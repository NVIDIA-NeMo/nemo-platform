# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Value types for standalone agent evaluation runs."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from nemo_evaluator_sdk.metrics.protocol import Metric, MetricOutput
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.values import Agent, Model, RunConfig, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.evidence import CandidateEvidence

AgentEvalAttemptStatus = Literal["completed", "failed", "partial"]
AgentEvalResultStatus = Literal["completed", "failed", "partial"]
AgentEvalDiagnosticSeverity = Literal["error", "warning", "info"]
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

    id: str
    run_id: str
    task_id: str
    attempt_id: str
    metric_type: str
    status: AgentEvalResultStatus = "completed"
    outputs: list[MetricOutput] = Field(default_factory=list)
    diagnostics: list["AgentEvalDiagnostic"] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvalDiagnostic(BaseModel):
    """Diagnostic emitted while scoring one attempt with one metric."""

    model_config = ConfigDict(extra="forbid")

    severity: AgentEvalDiagnosticSeverity = "error"
    message: str
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AgentEvalMetricOutputCoverage(BaseModel):
    """Coverage counts for one metric output across run results."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    scored: int = 0
    failed: int = 0
    missing: int = 0


class AgentEvalSummary(BaseModel):
    """Same-metric numeric rollups for an agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float | None = None
    metric_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    metric_coverage: dict[str, dict[str, AgentEvalMetricOutputCoverage]] = Field(default_factory=dict)
    semantic_view_scores: dict[str, float] = Field(default_factory=dict)
    task_count: int = 0
    attempt_count: int = 0
    result_count: int = 0

    @classmethod
    def from_results(
        cls,
        results: Sequence[AgentEvalTaskResult],
        *,
        tasks: Sequence[AgentEvalTask] | None = None,
    ) -> "AgentEvalSummary":
        """Build summary rollups and coverage for a set of metric results."""
        metric_values: dict[str, dict[str, list[float]]] = {}
        for result in results:
            if result.status != "completed":
                continue
            for output in result.outputs:
                value = _numeric_value(output)
                if value is None:
                    continue
                metric_values.setdefault(result.metric_type, {}).setdefault(output.name, []).append(value)

        metric_scores: dict[str, dict[str, float]] = {}
        for metric_type, outputs in sorted(metric_values.items()):
            output_scores = {
                output_name: score
                for output_name, values in sorted(outputs.items())
                if (score := mean_numeric(values)) is not None
            }
            if output_scores:
                metric_scores[metric_type] = output_scores

        rollup_values = [score for output_scores in metric_scores.values() for score in output_scores.values()]
        overall_score = rollup_values[0] if len(rollup_values) == 1 else None
        task_list = list(tasks) if tasks is not None else None
        return cls(
            overall_score=overall_score,
            metric_scores=metric_scores,
            metric_coverage=_metric_coverage(results, task_list),
            semantic_view_scores=_semantic_view_scores(results, task_list),
            task_count=len(task_list) if task_list is not None else len({result.task_id for result in results}),
            attempt_count=len({result.attempt_id for result in results}),
            result_count=len(results),
        )


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
    fail_fast: bool = False


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


def _metric_coverage(
    results: Sequence[AgentEvalTaskResult],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, dict[str, AgentEvalMetricOutputCoverage]]:
    output_names = _metric_output_names(results, tasks)
    coverage: dict[str, dict[str, AgentEvalMetricOutputCoverage]] = {}
    for metric_type, names in sorted(output_names.items()):
        metric_results = [result for result in results if result.metric_type == metric_type]
        metric_coverage: dict[str, AgentEvalMetricOutputCoverage] = {}
        for output_name in names:
            total = len(metric_results)
            failed = sum(1 for result in metric_results if result.status == "failed")
            scored = sum(
                1
                for result in metric_results
                if result.status != "failed" and any(output.name == output_name for output in result.outputs)
            )
            metric_coverage[output_name] = AgentEvalMetricOutputCoverage(
                total=total,
                scored=scored,
                failed=failed,
                missing=max(total - scored - failed, 0),
            )
        coverage[metric_type] = metric_coverage
    return coverage


def _metric_output_names(
    results: Sequence[AgentEvalTaskResult],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, list[str]]:
    names: dict[str, set[str]] = {}
    if tasks is not None:
        for task in tasks:
            for metric in task.metrics:
                metric_type = metric_type_name(metric)
                for output in metric.output_spec():
                    names.setdefault(metric_type, set()).add(output.name)

    for result in results:
        for output in result.outputs:
            names.setdefault(result.metric_type, set()).add(output.name)
    return {metric_type: sorted(output_names) for metric_type, output_names in names.items()}


def _semantic_view_scores(
    results: Sequence[AgentEvalTaskResult],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, float]:
    if tasks is None:
        return {}

    tasks_by_id = {task.id: task for task in tasks}
    result_by_key = {
        (result.task_id, result.attempt_id, result.metric_type): result
        for result in results
        if result.status == "completed"
    }
    attempts_by_task: dict[str, set[str]] = {}
    for result in results:
        attempts_by_task.setdefault(result.task_id, set()).add(result.attempt_id)

    values_by_view: dict[str, list[float]] = {}
    for task_id, attempt_ids in attempts_by_task.items():
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        for attempt_id in attempt_ids:
            for view_name, view in task.views.items():
                signal_values: list[float] = []
                for signal in view.signals:
                    result = result_by_key.get((task_id, attempt_id, signal.metric))
                    output = _result_output(result, signal.output) if result is not None else None
                    value = _semantic_value(output) if output is not None else None
                    if value is None:
                        signal_values = []
                        break
                    signal_values.append(value)
                if not signal_values:
                    continue
                reduced = _reduce_semantic_view(view.reducer, signal_values, view.signals)
                if reduced is not None:
                    values_by_view.setdefault(view_name, []).append(reduced)

    return {
        view_name: score
        for view_name, values in sorted(values_by_view.items())
        if (score := mean_numeric(values)) is not None
    }


def _result_output(result: AgentEvalTaskResult | None, output_name: str) -> MetricOutput | None:
    if result is None:
        return None
    for output in result.outputs:
        if output.name == output_name:
            return output
    return None


def _reduce_semantic_view(
    reducer: SemanticReducer,
    values: list[float],
    signals: list[ViewSignal],
) -> float | None:
    if reducer == "single":
        return values[0]
    if reducer == "all":
        return min(values)
    if reducer == "any":
        return max(values)
    if reducer == "mean":
        return mean_numeric(values)
    weights = [signal.weight if signal.weight is not None else 1.0 for signal in signals]
    denominator = sum(weights)
    if denominator == 0:
        return None
    return sum(value * weight for value, weight in zip(values, weights, strict=True)) / denominator


def _numeric_value(output: MetricOutput) -> float | None:
    value = output.value
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, BaseModel):
        root = getattr(value, "root", None)
        if isinstance(root, bool):
            return None
        if isinstance(root, int | float):
            return float(root)
    return None


def _semantic_value(output: MetricOutput) -> float | None:
    value = output.value
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, BaseModel):
        root = getattr(value, "root", None)
        if isinstance(root, bool):
            return 1.0 if root else 0.0
    return _numeric_value(output)


def mean_numeric(values: list[float]) -> float | None:
    """Return the mean of finite numeric values, ignoring missing and NaN."""
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return None
    return sum(finite) / len(finite)


AgentEvalTarget = Model | Agent | AgentAttemptRuntime
