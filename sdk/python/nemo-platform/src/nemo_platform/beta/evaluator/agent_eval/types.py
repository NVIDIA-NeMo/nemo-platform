# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Value types for standalone agent evaluation runs."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from nemo_platform.beta.evaluator.metrics.protocol import Metric, MetricOutput
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence

AgentEvalAttemptStatus = Literal["completed", "failed", "partial"]
SemanticReducer = Literal["single", "all", "any", "mean", "weighted_mean"]


class ViewSignal(BaseModel):
    """Task-local metric output that contributes to a semantic view."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    output: str
    weight: float | None = None

    @field_validator("metric", "output")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("view signal metric and output must not be empty")
        return value


class SemanticView(BaseModel):
    """Task-local reporting view over metric outputs."""

    model_config = ConfigDict(extra="forbid")

    reducer: SemanticReducer
    signals: list[ViewSignal] = Field(min_length=1)


class AgentOutput(BaseModel):
    """Output produced by an evaluated agent or imported baseline response."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    text: str | None = Field(default=None, validation_alias=AliasChoices("text", "output_text"))
    response: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def output_text(self) -> str | None:
        """Compatibility projection matching ``CandidateOutput.output_text``."""
        return self.text


class AgentEvalTask(BaseModel):
    """Standalone agent-eval task."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    id: str
    intent: str
    inputs: dict[str, Any]
    metrics: list[Metric] = Field(default_factory=list)
    views: dict[str, SemanticView] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

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
    def _validate_metric_references(self) -> "AgentEvalTask":
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


class AgentEvalAttempt(BaseModel):
    """Stored or generated candidate attempt for one task."""

    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    status: AgentEvalAttemptStatus = "completed"
    output: AgentOutput | None = None
    evidence: CandidateEvidence | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "task_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("attempt id and task_id must not be empty")
        return value

    @model_validator(mode="after")
    def _completed_attempt_requires_output(self) -> "AgentEvalAttempt":
        if self.status == "completed" and self.output is None:
            raise ValueError("completed attempt requires output")
        return self


class AgentEvalTaskResult(BaseModel):
    """Metric result for one task attempt."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    attempt_id: str
    metric_type: str
    outputs: list[MetricOutput]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvalSummary(BaseModel):
    """Same-metric numeric rollups for an agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float | None = None
    metric_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    task_count: int = 0
    attempt_count: int = 0
    result_count: int = 0


class AgentEvalRunConfig(BaseModel):
    """Configuration for a standalone agent-eval run."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    output_dir: Path | None = None
    run_id: str | None = None
    prompt_template: str | dict[str, Any] | None = None
    params: RunConfig | RunConfigOnline | RunConfigOnlineModel | None = None
    parallelism: int = Field(default=4, ge=1)
    model_inference_fn: Any | None = Field(default=None, exclude=True)
    agent_inference_fn: Any | None = Field(default=None, exclude=True)
    model_client: Any | None = Field(default=None, exclude=True)
    agent_client: Any | None = Field(default=None, exclude=True)
    default_headers: dict[str, str] | None = None
    write_dashboard: bool = True
    benchmark: dict[str, Any] = Field(default_factory=dict)


class AgentEvalRunResult(BaseModel):
    """Completed standalone agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    tasks: list[AgentEvalTask]
    attempts: list[AgentEvalAttempt]
    results: list[AgentEvalTaskResult]
    summary: AgentEvalSummary
    benchmark: dict[str, Any] = Field(default_factory=dict)
    output_dir: Path | None = None
    dashboard_path: Path | None = None


@runtime_checkable
class AgentAttemptRuntime(Protocol):
    """Runtime that produces agent-eval attempts for supplied tasks."""

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalAttempt]: ...


def mean_numeric(values: list[float]) -> float | None:
    """Return the mean of finite numeric values, ignoring missing and NaN."""
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return None
    return sum(finite) / len(finite)


AgentEvalTarget = Model | Agent | AgentAttemptRuntime
