# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Aggregated summary, coverage, and the root result for a completed agent evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalTask, SemanticReducer, ViewSignal
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial
from nemo_platform.beta.evaluator.metrics.protocol import MetricOutput
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.values.results import AggregatedMetricResult, AggregateRangeScore, AggregateScore
from pydantic import BaseModel, ConfigDict, Field


class AgentEvalMetricOutputCoverage(BaseModel):
    """Coverage counts for one metric output across scored trials."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(default=0, description="Total scores considered for this metric output.")
    scored: int = Field(default=0, description="Scores that produced this output successfully.")
    failed: int = Field(default=0, description="Scores where the metric failed to run.")
    missing: int = Field(default=0, description="Scores where the output was expected but absent.")


class AgentEvalSummary(BaseModel):
    """Aggregated metric and semantic-view scores, coverage, and run counts for an agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    scores: AggregatedMetricResult = Field(
        default_factory=lambda: AggregatedMetricResult(scores=[]),
        description=(
            "Aggregated statistics (mean/min/max/std_dev/nan_count) per metric output, named "
            "'<metric_type>.<output>', plus per-semantic-view rollups named 'view.<name>'. "
            "Failed or missing scores are surfaced as nan_count."
        ),
    )
    metric_coverage: dict[str, dict[str, AgentEvalMetricOutputCoverage]] = Field(
        default_factory=dict,
        description="Per-metric, per-output coverage counts (total/scored/failed/missing).",
    )
    task_count: int = Field(default=0, description="Number of tasks represented in the run.")
    trial_count: int = Field(default=0, description="Number of distinct trials scored.")
    score_count: int = Field(default=0, description="Total number of metric scores.")

    @staticmethod
    def from_scores(
        scores: Sequence[AgentEvalTaskScore],
        *,
        tasks: Sequence[AgentEvalTask] | None = None,
    ) -> AgentEvalSummary:
        """Build aggregated scores and coverage for a set of metric scores."""
        task_list = list(tasks) if tasks is not None else None
        return AgentEvalSummary(
            scores=_aggregate_scores(scores, task_list),
            metric_coverage=_metric_coverage(scores, task_list),
            task_count=len(task_list) if task_list is not None else len({score.task_id for score in scores}),
            trial_count=len({score.trial_id for score in scores}),
            score_count=len(scores),
        )


class AgentEvalResult(BaseModel):
    """Root result for a completed agent evaluation: tasks, trials, scores, summary, and bundle metadata."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Identifier of this run.")
    tasks: list[AgentEvalTask] = Field(description="Immutable task definitions evaluated in this run.")
    trials: list[AgentEvalTrial] = Field(description="Trials produced or imported for the run.")
    scores: list[AgentEvalTaskScore] = Field(description="Metric scores computed for the trials.")
    summary: AgentEvalSummary = Field(description="Derived rollups and coverage computed for the run.")
    benchmark: dict[str, Any] = Field(
        default_factory=dict,
        description="Benchmark metadata recorded for the run.",
    )
    output_dir: Path | None = Field(default=None, description="Directory the run bundle was written to, if any.")
    dashboard_path: Path | None = Field(default=None, description="Path to the rendered dashboard, if written.")


def _aggregate_scores(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
) -> AggregatedMetricResult:
    """Aggregate per-metric-output and per-semantic-view values into range scores.

    Each metric output becomes a score named ``<metric_type>.<output>`` and each
    semantic view a score named ``view.<name>``. Failed and missing scores are
    surfaced as ``nan_count`` so coverage is visible alongside the statistics.
    """
    aggregated: list[AggregateScore] = []

    output_names = _metric_output_names(scores, tasks)
    for metric_type, names in sorted(output_names.items()):
        metric_records = [score for score in scores if score.metric_type == metric_type]
        total = len(metric_records)
        for output_name in names:
            values: list[float] = []
            for score in metric_records:
                value = None
                # PARTIAL scores can still emit valid per-output values; include them so
                # stats agree with coverage (which counts non-FAILED outputs as scored).
                # Outputs actually missing on a PARTIAL score stay None -> counted as nan.
                if score.status in (AgentEvalScoreStatus.COMPLETED, AgentEvalScoreStatus.PARTIAL):
                    output = _score_output(score, output_name)
                    value = _numeric_value(output) if output is not None else None
                if value is not None:
                    values.append(value)
            aggregated.append(_aggregate_range_score(f"{metric_type}.{output_name}", values, total))

    for view_name, (values, total) in sorted(_semantic_view_values(scores, tasks).items()):
        aggregated.append(_aggregate_range_score(f"view.{view_name}", values, total))

    return AggregatedMetricResult(scores=aggregated)


def _aggregate_range_score(name: str, values: list[float], total: int) -> AggregateRangeScore:
    finite = [value for value in values if math.isfinite(value)]
    count = len(finite)
    nan_count = max(total - count, 0)
    if not finite:
        return AggregateRangeScore(name=name, count=0, nan_count=nan_count)
    total_sum = sum(finite)
    mean = total_sum / count
    variance = sum((value - mean) ** 2 for value in finite) / count
    return AggregateRangeScore(
        name=name,
        count=count,
        nan_count=nan_count,
        sum=total_sum,
        mean=mean,
        min=min(finite),
        max=max(finite),
        variance=variance,
        std_dev=math.sqrt(variance),
    )


def _metric_coverage(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, dict[str, AgentEvalMetricOutputCoverage]]:
    output_names = _metric_output_names(scores, tasks)
    coverage: dict[str, dict[str, AgentEvalMetricOutputCoverage]] = {}
    for metric_type, names in sorted(output_names.items()):
        metric_records = [score for score in scores if score.metric_type == metric_type]
        metric_coverage: dict[str, AgentEvalMetricOutputCoverage] = {}
        for output_name in names:
            total = len(metric_records)
            failed = sum(1 for score in metric_records if score.status == AgentEvalScoreStatus.FAILED)
            scored = sum(
                1
                for score in metric_records
                if score.status != AgentEvalScoreStatus.FAILED
                and any(output.name == output_name for output in score.outputs)
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
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, list[str]]:
    names: dict[str, set[str]] = {}
    if tasks is not None:
        for task in tasks:
            for metric in task.metrics:
                metric_type = metric_type_name(metric)
                for output in metric.output_spec():
                    names.setdefault(metric_type, set()).add(output.name)

    for score in scores:
        for output in score.outputs:
            names.setdefault(score.metric_type, set()).add(output.name)
    return {metric_type: sorted(output_names) for metric_type, output_names in names.items()}


def _semantic_view_values(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, tuple[list[float], int]]:
    """Return reduced view values and the number of attempted reductions per view.

    The integer in each tuple is the total number of trial/view reductions
    attempted (the denominator for nan_count); the list holds the values that
    reduced successfully.
    """
    if tasks is None:
        return {}

    tasks_by_id = {task.id: task for task in tasks}
    # Match the stats path: PARTIAL scores may carry usable signal outputs. Missing
    # signals still skip the view reduction below, so admitting PARTIAL is safe.
    score_by_key = {
        (score.task_id, score.trial_id, score.metric_type): score
        for score in scores
        if score.status in (AgentEvalScoreStatus.COMPLETED, AgentEvalScoreStatus.PARTIAL)
    }
    trials_by_task: dict[str, set[str]] = {}
    for score in scores:
        trials_by_task.setdefault(score.task_id, set()).add(score.trial_id)

    values_by_view: dict[str, list[float]] = {}
    totals_by_view: dict[str, int] = {}
    for task_id, trial_ids in trials_by_task.items():
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        for trial_id in trial_ids:
            for view_name, view in task.views.items():
                totals_by_view[view_name] = totals_by_view.get(view_name, 0) + 1
                signal_values: list[float] = []
                for signal in view.signals:
                    score = score_by_key.get((task_id, trial_id, signal.metric))
                    output = _score_output(score, signal.output) if score is not None else None
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

    return {view_name: (values_by_view.get(view_name, []), total) for view_name, total in totals_by_view.items()}


def _score_output(score: AgentEvalTaskScore | None, output_name: str) -> MetricOutput | None:
    if score is None:
        return None
    for output in score.outputs:
        if output.name == output_name:
            return output
    return None


def _reduce_semantic_view(
    reducer: SemanticReducer,
    values: list[float],
    signals: list[ViewSignal],
) -> float | None:
    if reducer == SemanticReducer.SINGLE:
        return values[0]
    if reducer == SemanticReducer.ALL:
        return min(values)
    if reducer == SemanticReducer.ANY:
        return max(values)
    if reducer == SemanticReducer.MEAN:
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
