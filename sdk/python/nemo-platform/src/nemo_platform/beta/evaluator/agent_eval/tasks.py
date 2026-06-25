# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task definitions, semantic views, and run configuration for agent evaluation."""

from __future__ import annotations

import importlib
from enum import Enum
from typing import Any, Protocol, TypeGuard, runtime_checkable
from pathlib import Path

from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator, field_serializer

from nemo_platform.beta.evaluator.values import RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.metrics.protocol import Metric


class SemanticReducer(str, Enum):
    """Reduction strategy used to combine task-scoped view signals into one score."""

    SINGLE = "single"
    ALL = "all"
    ANY = "any"
    MEAN = "mean"
    WEIGHTED_MEAN = "weighted_mean"


class ViewSignal(BaseModel):
    """Task-scoped metric output that contributes to a semantic view."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(description="Task-local metric type (metric.type) whose output feeds this signal.")
    output: str = Field(description="Name of the metric output, as declared by the metric's output_spec().")
    weight: float | None = Field(
        default=None,
        description="Relative weight for this signal when the view reducer is 'weighted_mean'; unused otherwise.",
    )

    @field_validator("metric", "output")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("view signal metric and output must not be empty")
        return value


class SemanticView(BaseModel):
    """Task-scoped reporting view that maps a task's own metric outputs into a named score."""

    model_config = ConfigDict(extra="forbid")

    reducer: SemanticReducer = Field(
        description="Strategy used to reduce this view's signals into a single task-level score.",
    )
    signals: list[ViewSignal] = Field(
        min_length=1,
        description="Ordered metric outputs contributing to this view; at least one is required.",
    )


class AgentEvalTask(BaseModel):
    """Standalone agent-eval task: the unit of work being evaluated."""

    # TODO: Tasks may need to define a set of required_capabilities or something that allow the
    # runtime to skip trying to complete a task that isn't possible.
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    id: str = Field(description="Stable task identifier, unique within the supplied task collection.")
    intent: str = Field(description="Human-readable description of the desired agent behavior.")
    inputs: dict[str, Any] = Field(
        description="What the agent receives or starts from, e.g. instruction, filesystem seed, or state refs.",
    )
    metrics: list[Metric] = Field(
        default_factory=list,
        description="Ordered concrete SDK metric instances that score this task; metric types must be unique.",
    )
    views: dict[str, SemanticView] = Field(
        default_factory=dict,
        description="Optional reporting views mapping this task's metric outputs into named semantic scores.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the task.",
    )

    @field_validator("id")
    @classmethod
    def _id_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("task id must not be empty")
        return value

    @field_serializer("metrics", when_used="json")
    def _serialize_metrics(self, metrics: list[Metric]) -> list[dict[str, Any]]:
        """Serialize local metric instances as descriptors for run bundles."""
        serialized: list[dict[str, Any]] = []
        for metric in metrics:
            outputs = [
                {
                    "name": output.name,
                    "description": output.description,
                    "value_schema": output.value_schema.__name__,
                }
                for output in metric.output_spec()
            ]
            serialized.append({"type": metric_type_name(metric), "outputs": outputs})
        return serialized

    @model_validator(mode="after")
    def _validate_metric_references(self) -> AgentEvalTask:
        metric_types = [metric_type_name(metric) for metric in self.metrics]
        duplicate_metric_types = sorted(
            {metric_type for metric_type in metric_types if metric_types.count(metric_type) > 1}
        )
        if duplicate_metric_types:
            raise ValueError(f"duplicate task metric types: {duplicate_metric_types}")

        outputs_by_metric = {
            metric_type_name(metric): {output.name for output in metric.output_spec()} for metric in self.metrics
        }
        for view_name, view in self.views.items():
            for signal in view.signals:
                if signal.metric not in outputs_by_metric:
                    raise ValueError(f"view {view_name!r} references unknown metric {signal.metric!r}")
                if signal.output not in outputs_by_metric[signal.metric]:
                    raise ValueError(
                        f"view {view_name!r} references unknown output {signal.output!r} for metric {signal.metric!r}"
                    )
        return self


class AgentEvalTasksetLoadConfig(BaseModel):
    """Options passed from callers to a taskset's :meth:`AgentEvalTaskset.load`."""

    model_config = ConfigDict(extra="forbid")

    source: str | Path | None = Field(default=None, description="Optional source path/URI the taskset loads from.")
    limit: int | None = Field(default=None, ge=0, description="Optional cap on the number of tasks to load.")
    evidence_dir: Path | None = Field(default=None, description="Optional directory holding task evidence inputs.")


class AgentEvalTasksetBundle(BaseModel):
    """SDK-native tasks (and optional metadata) produced by a taskset's ``load()``."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[AgentEvalTask] = Field(default_factory=list, description="Loaded tasks; at least one is required.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form taskset metadata for the run.")

    @model_validator(mode="after")
    def _require_tasks(self) -> AgentEvalTasksetBundle:
        if not self.tasks:
            raise ValueError("taskset bundles require at least one task")
        return self


@runtime_checkable
class AgentEvalTaskset(Protocol):
    """Experimental protocol for adapting external tasksets into agent-eval.

    A taskset is a named *adapter* that loads SDK-native tasks (optionally from an
    external source). Per the design, tasksets are resolved upstream into
    :class:`AgentEvalTask` values via :func:`resolve_agent_eval_taskset`; the
    evaluator scores those tasks and never consumes a taskset directly.
    """

    @property
    def name(self) -> str:
        """Stable taskset name used in diagnostics, metadata, and user-facing output."""
        ...

    def load(self, config: AgentEvalTasksetLoadConfig) -> AgentEvalTasksetBundle:
        """Load this taskset's tasks (and optional metadata) into SDK-native form."""
        ...


def _is_agent_eval_taskset(value: object) -> TypeGuard[AgentEvalTaskset]:
    return isinstance(getattr(value, "name", None), str) and callable(getattr(value, "load", None))


def resolve_agent_eval_taskset(ref: str) -> AgentEvalTaskset:
    """Resolve a ``module:object`` taskset reference.

    The referenced object may be a taskset instance, a taskset class, or a
    zero-argument factory returning a taskset instance.
    """
    module_name, separator, object_path = ref.partition(":")
    if not separator or not module_name or not object_path:
        raise ValueError("taskset references must use module:object syntax")

    resolved: Any = importlib.import_module(module_name)
    for part in object_path.split("."):
        resolved = getattr(resolved, part)

    candidate = resolved
    if isinstance(candidate, type):
        candidate = candidate()
    elif not _is_agent_eval_taskset(candidate) and callable(candidate):
        candidate = candidate()

    if not _is_agent_eval_taskset(candidate):
        raise TypeError(f"resolved taskset {ref!r} does not implement AgentEvalTaskset")
    return candidate


class AgentEvalRunConfig(BaseModel):
    """Configuration for a standalone agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    output_dir: Path | None = Field(
        default=None,
        description="Directory where the run bundle is written; in-memory only when omitted.",
    )
    run_id: str | None = Field(default=None, description="Explicit run identifier; generated when omitted.")
    prompt_template: str | dict[str, Any] | None = Field(
        default=None,
        description="Optional prompt template applied when generating trials online.",
    )
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = Field(
        default=None,
        description="Inference/run parameters used when producing trials online.",
    )
    parallelism: int = Field(default=4, ge=1, description="Maximum number of tasks scored concurrently.")
    write_dashboard: bool = Field(default=True, description="Whether to render an HTML dashboard for the run.")
    benchmark: dict[str, Any] = Field(
        default_factory=dict,
        description="Benchmark metadata recorded alongside the run.",
    )
    fail_fast: bool = Field(default=False, description="Stop the run on the first scoring failure when True.")
