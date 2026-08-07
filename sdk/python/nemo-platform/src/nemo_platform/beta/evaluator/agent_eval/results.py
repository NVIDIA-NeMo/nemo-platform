# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Aggregated summary, coverage, and the root result for a completed agent evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from nemo_platform.beta.evaluator.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore, is_trial_failure
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalTask, SemanticReducer, ViewSignal
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial, RunnerInfo
from nemo_platform.beta.evaluator.metrics.aggregation import compute_percentiles
from nemo_platform.beta.evaluator.metrics.protocol import MetricOutput
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.values.protocol import BooleanValue, ContinuousScore
from nemo_platform.beta.evaluator.values.results import AggregatedMetricResult, AggregateRangeScore, AggregateScore
from pydantic import BaseModel, ConfigDict, Field

#: Metric-output value schemas eligible for pass@k (a per-attempt "did it pass?" signal). Labels,
#: discrete/count outputs, and free models (e.g. token measurements) are excluded.
_PASS_AT_K_VALUE_SCHEMAS = (ContinuousScore, BooleanValue)

#: Score value at or above which an attempt counts as a pass for pass@k. Full credit — pass@k answers
#: "did the agent solve the task", so partial credit is not a pass. Deliberately not configurable:
#: it's a reporting-time interpretation, and making it tunable would yield pass@k numbers that look
#: comparable across runs but aren't.
_PASS_VALUE = 1.0


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
        extra_scores: Sequence[AggregateScore] = (),
    ) -> AgentEvalSummary:
        """Build aggregated scores and coverage for a set of metric scores.

        ``extra_scores`` are already-aggregated scores contributed by the runner (namespaced
        ``runner.<name>.``), merged in so a backend's own figures are addressable the same way as ours.
        """
        task_list = list(tasks) if tasks is not None else None
        return AgentEvalSummary(
            scores=_aggregate_scores(scores, task_list, extra_scores),
            metric_coverage=_metric_coverage(scores, task_list),
            task_count=len(task_list) if task_list is not None else len({score.task_id for score in scores}),
            trial_count=len({score.trial_id for score in scores}),
            score_count=len(scores),
        )


class RunMetadata(BaseModel):
    """Provenance for a run: what was evaluated, by what, and when.

    Answers "what produced this result?" — previously improvised by callers inside an untyped
    ``benchmark`` dict. ``labels`` remains free-form for caller-specific tags, but the fields that
    every run has are typed.
    """

    model_config = ConfigDict(extra="forbid")

    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Caller-supplied tags for this run (e.g. benchmark, mode, backend). Free-form by design.",
    )
    target: RunnerInfo | None = Field(
        default=None,
        description="Identity of the runner/model/agent that produced the trials; None for imported trials.",
    )
    started_at: datetime | None = Field(default=None, description="UTC timestamp when the run began.")
    finished_at: datetime | None = Field(default=None, description="UTC timestamp when scoring completed.")
    duration_sec: float | None = Field(default=None, description="Wall-clock seconds from start to finish.")
    sdk_version: str | None = Field(default=None, description="nemo-evaluator-sdk version that produced the run.")


class AgentEvalResult(BaseModel):
    """Root result for a completed agent evaluation: tasks, trials, scores, summary, and bundle metadata."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Identifier of this run.")
    tasks: list[AgentEvalTask] = Field(description="Immutable task definitions evaluated in this run.")
    trials: list[AgentEvalTrial] = Field(description="Trials produced or imported for the run.")
    scores: list[AgentEvalTaskScore] = Field(description="Metric scores computed for the trials.")
    summary: AgentEvalSummary = Field(description="Derived rollups and coverage computed for the run.")
    metadata: RunMetadata = Field(
        default_factory=RunMetadata,
        description="Run provenance: labels, target identity, timings, SDK version.",
    )
    output_dir: Path | None = Field(default=None, description="Directory the run bundle was written to, if any.")
    dashboard_path: Path | None = Field(default=None, description="Path to the rendered dashboard, if written.")


def _aggregate_scores(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
    extra_scores: Sequence[AggregateScore] = (),
) -> AggregatedMetricResult:
    """Aggregate per-metric-output, per-semantic-view, and task-level pass@k values into range scores.

    Each metric output becomes a score named ``<metric_type>.<output>``, each semantic view
    ``view.<name>``, and each score-like output additionally yields ``<metric_type>.<output>.pass@k``
    task-level rollups. Failed and missing scores are surfaced as ``nan_count`` so coverage is visible
    alongside the statistics. ``extra_scores`` (runner-contributed, ``runner.``-namespaced) are appended
    as-is.
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

    aggregated.extend(_task_pass_at_k_scores(scores, tasks))
    aggregated.extend(extra_scores)

    return AggregatedMetricResult(scores=aggregated)


def _pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k estimator (Chen et al., 2021): ``1 - C(n-c, k) / C(n, k)``.

    The probability that at least one of ``k`` samples drawn without replacement from ``n`` attempts
    (``c`` of them passing) is a pass. Caller guarantees ``1 <= k <= n``.
    """
    if n - c < k:
        return 1.0
    product = 1.0
    for i in range(n - c + 1, n + 1):
        product *= 1.0 - k / i
    return 1.0 - product


def _scorelike_outputs(tasks: Sequence[AgentEvalTask] | None) -> set[tuple[str, str]]:
    """``(metric_type, output_name)`` pairs whose declared value is a score (continuous or boolean).

    pass@k is only meaningful for a per-attempt pass/fail signal, so labels, discrete/count outputs,
    and free models (e.g. token measurements) are excluded. Needs task metric specs; with no tasks
    the set is empty and pass@k is skipped.
    """
    scorelike: set[tuple[str, str]] = set()
    if tasks is None:
        return scorelike
    for task in tasks:
        for metric in task.metrics:
            metric_type = metric_type_name(metric)
            for spec in metric.output_spec():
                if issubclass(spec.value_schema, _PASS_AT_K_VALUE_SCHEMAS):
                    scorelike.add((metric_type, spec.name))
    return scorelike


def _task_pass_at_k_scores(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
) -> list[AggregateScore]:
    """Task-level pass@k over the R trials per task, aggregated across tasks (uniform for any runner).

    For each score-like metric output, group trials by task, count attempts ``n`` and passes ``c``
    (value ``>= _PASS_VALUE``), then emit ``<metric>.<output>.pass@k`` for ``k`` in ``1..max(n)`` as
    the across-task mean of the unbiased per-task estimator (over tasks with at least ``k`` attempts).
    ``pass@1`` equals the macro per-task pass rate, i.e. the task-level mean.

    **A failed trial is a failed attempt.** It counts toward ``n`` and never toward ``c``: an agent that
    solved a task once and crashed once did not go one-for-one. A failed *metric* is different — it
    leaves the attempt unmeasured rather than unsuccessful, so it stays out of ``n`` entirely rather
    than being charged to the agent (see :func:`is_trial_failure`). Tasks left with no usable attempt at
    all drop out of the estimate and are reported as ``nan_count``, uniform across ``k``, so a shrinking
    denominator is never silent. (Tasks excluded from a given ``k`` merely for having fewer than ``k``
    attempts are *not* counted there — that is the estimator working as defined, not missing data.)
    """
    scorelike = _scorelike_outputs(tasks)
    if not scorelike:
        return []
    aggregated: list[AggregateScore] = []
    for metric_type, output_name in sorted(scorelike):
        attempts_and_passes: dict[str, list[int]] = {}  # task_id -> [n_attempts, n_passes]
        tasks_seen: set[str] = set()
        for score in scores:
            if score.metric_type != metric_type:
                continue
            tasks_seen.add(score.task_id)
            if is_trial_failure(score):
                # The agent produced nothing to score. That is an attempt that did not pass, not an
                # attempt that did not happen -- dropping it would report pass@1 = 1.0 for a run whose
                # other rollout died, and make pass@2 vanish along with the attempt that justified it.
                attempts_and_passes.setdefault(score.task_id, [0, 0])[0] += 1
                continue
            if score.status not in (AgentEvalScoreStatus.COMPLETED, AgentEvalScoreStatus.PARTIAL):
                # The metric raised, so whether this attempt passed is unknown. Charging it to the agent
                # would let a judge timeout read as a task the agent failed; it lands in nan_count.
                continue
            output = _score_output(score, output_name)
            value = _semantic_value(output) if output is not None else None
            if value is None:
                continue
            counts = attempts_and_passes.setdefault(score.task_id, [0, 0])
            counts[0] += 1
            if value >= _PASS_VALUE:
                counts[1] += 1
        if not attempts_and_passes:
            continue
        # Tasks that were scored for this metric but yielded no usable attempt whatsoever. Constant
        # across k, so pass@1 and pass@8 agree on how much of the task set went unmeasured.
        unmeasured = len(tasks_seen - set(attempts_and_passes))
        max_n = max(n for n, _ in attempts_and_passes.values())
        for k in range(1, max_n + 1):
            per_task = [_pass_at_k(n, c, k) for n, c in attempts_and_passes.values() if n >= k]
            if per_task:
                aggregated.append(
                    _aggregate_range_score(
                        f"{metric_type}.{output_name}.pass@{k}", per_task, len(per_task) + unmeasured
                    )
                )
    return aggregated


def _aggregate_range_score(name: str, values: list[float], total: int) -> AggregateRangeScore:
    finite = [value for value in values if math.isfinite(value)]
    count = len(finite)
    nan_count = max(total - count, 0)
    if not finite:
        return AggregateRangeScore(name=name, count=0, nan_count=nan_count)
    total_sum = sum(finite)
    mean = total_sum / count
    # Report both conventions explicitly rather than picking one: the population figures describe the
    # values actually evaluated, the sample figures estimate the process they were drawn from (which is
    # what repeated trials over one task are sampling). Sample stats are undefined for a single value.
    sum_sq_dev = sum((value - mean) ** 2 for value in finite)
    variance = sum_sq_dev / count
    sample_variance = sum_sq_dev / (count - 1) if count > 1 else None
    percentiles = compute_percentiles(sorted(finite))
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
        sample_variance=sample_variance,
        sample_std_dev=math.sqrt(sample_variance) if sample_variance is not None else None,
        # Reuse the deterministic-metric percentile helper so agent-eval and metric aggregation report
        # the same distribution the same way.
        percentiles=percentiles,
        # Surfaced alongside the other basic stats so `median` means the same thing whether a score
        # was computed here or imported from a backend that reports one without a full distribution.
        median=percentiles.p50,
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
