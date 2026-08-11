# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Aggregated summary, coverage, and the root result for a completed agent evaluation."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.scores import (
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
    is_trial_failure,
)
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalTask, SemanticReducer, ViewSignal
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial, RunnerInfo
from nemo_platform.beta.evaluator.metrics.aggregation import compute_percentiles
from nemo_platform.beta.evaluator.metrics.protocol import MetricOutput
from nemo_platform.beta.evaluator.metrics.utils import metric_type_name
from nemo_platform.beta.evaluator.values.protocol import BooleanValue, ContinuousScore, DiscreteScore
from nemo_platform.beta.evaluator.values.results import (
    AggregatedMetricResult,
    AggregateRangeScore,
    AggregateScore,
    ResultView,
    flatten_dict,
    format_table,
    serialize_value,
    summary_aggregate_record,
)
from pydantic import BaseModel, ConfigDict, Field

#: Metric-output value schemas retained in the ordered per-task attempt mapping.
_TASK_METRIC_VALUE_SCHEMAS = (ContinuousScore, DiscreteScore, BooleanValue)

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


class AgentEvalAttemptValue(BaseModel):
    """One attempt at a task under one metric output: which trial made it, and what it measured.

    Frozen because these records are handed out by reference from the summary: a consumer rescaling
    values in place (Gym reports reward on 0-100 where we use 0-1) would otherwise rewrite the run's
    own results, and a later persist would save the rewrite.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trial_id: str = Field(
        description=(
            "Identifier of the trial that made this attempt. Joins to AgentEvalTrial.id "
            "(trials.jsonl) and AgentEvalTaskScore.trial_id (scores.jsonl)."
        )
    )
    value: float | None = Field(
        description=(
            "What the metric output measured, or None when the trial failed before it could be "
            "measured -- an attempt that did not pass. Required rather than defaulted: None is a "
            "load-bearing signal pass@k counts as a failed attempt, so an omitted value must not "
            "quietly become one."
        ),
    )


class AgentEvalSummary(BaseModel):
    """Aggregated scores, coverage, per-task attempt values, and run counts for an agent-eval run."""

    model_config = ConfigDict(extra="forbid")

    scores: AggregatedMetricResult = Field(
        default_factory=lambda: AggregatedMetricResult(scores=[]),
        description=(
            "Aggregated statistics (mean/min/max/std_dev/nan_count) per metric output, named "
            "'<metric_type>.<output>', plus per-semantic-view rollups named 'view.<name>'. "
            "Failed or missing scores are surfaced as nan_count."
        ),
        examples=[
            # Emission order is real: metric outputs, then views, then pass@k. Note that pass@k
            # counts *tasks* (4) where the metric output counts *trials* (10).
            {
                "scores": [
                    {
                        "name": "harbor_reward.reward",
                        "score_type": "range",
                        "count": 10,
                        "nan_count": 2,
                        "mean": 0.6,
                        "min": 0.0,
                        "max": 1.0,
                        "std_dev": 0.4899,
                    },
                    {
                        "name": "view.legal_quality",
                        "score_type": "range",
                        "count": 8,
                        "nan_count": 4,
                        "mean": 0.7375,
                        "min": 0.1,
                        "max": 1.0,
                        "std_dev": 0.3674,
                    },
                    {
                        "name": "harbor_reward.reward.pass@1",
                        "score_type": "range",
                        "count": 4,
                        "nan_count": 1,
                        "mean": 0.5,
                        "min": 0.0,
                        "max": 1.0,
                        "std_dev": 0.3727,
                    },
                    {
                        "name": "harbor_reward.reward.pass@2",
                        "score_type": "range",
                        "count": 4,
                        "nan_count": 1,
                        "mean": 0.6667,
                        "min": 0.0,
                        "max": 1.0,
                        "std_dev": 0.4082,
                    },
                ]
            },
            # A separate run, because a runner's imported figures cannot co-occur with another
            # runner's metrics. Scalars carry `value` and no distribution, and no `count` when the
            # backend reports a figure without the sample size behind it.
            {
                "scores": [
                    {
                        "name": "gym_reward.reward",
                        "score_type": "range",
                        "count": 20,
                        "nan_count": 0,
                        "mean": 0.65,
                        "min": 0.0,
                        "max": 1.0,
                        "std_dev": 0.477,
                    },
                    {"name": "runner.gym.pass@1/accuracy", "score_type": "scalar", "nan_count": 0, "value": 0.68},
                ]
            },
        ],
    )
    metric_coverage: dict[str, dict[str, AgentEvalMetricOutputCoverage]] = Field(
        default_factory=dict,
        description="Per-metric, per-output coverage counts (total/scored/failed/missing).",
        examples=[
            # Same 12 trials under two metrics, which is what distinguishes a low mean from low
            # coverage. The two dead trials fail every metric; the judge failed once more on its own,
            # and once completed without emitting its output at all (missing, not failed).
            {
                "harbor_reward": {"reward": {"total": 12, "scored": 10, "failed": 2, "missing": 0}},
                "rubric_judge": {"criteria_pass_rate": {"total": 12, "scored": 8, "failed": 3, "missing": 1}},
            }
        ],
    )
    task_metric_attempts: dict[str, dict[str, list[AgentEvalAttemptValue]]] = Field(
        default_factory=dict,
        description=(
            "Per task, the attempts each '<metric_type>.<output>' measured, in trial order. Each "
            "attempt names the trial that made it, so attempts join across keys -- and out to "
            "trials.jsonl and scores.jsonl -- by trial_id. A failed trial has value None: an attempt "
            "that did not pass. An unmeasured attempt (metric failed, output absent) has no entry at "
            "all, so each key's list is independent: align by trial_id, never by position. An empty "
            "list means nothing was measured, including a task that produced no trial."
        ),
        examples=[
            {
                "contract-review-msa-indemnity": {
                    "harbor_reward.reward": [
                        {"trial_id": "contract-review-msa-indemnity__k3f9wq2", "value": 1.0},
                        {"trial_id": "contract-review-msa-indemnity__t7m2xb4", "value": 0.0},
                        {"trial_id": "contract-review-msa-indemnity__9jr4vd1", "value": 1.0},
                    ],
                    # t7m2xb4 is absent here rather than null: its judge timed out, so that attempt
                    # went unmeasured. Index 1 is therefore a different trial in each of these lists.
                    "rubric_judge.criteria_pass_rate": [
                        {"trial_id": "contract-review-msa-indemnity__k3f9wq2", "value": 0.75},
                        {"trial_id": "contract-review-msa-indemnity__9jr4vd1", "value": 1.0},
                    ],
                },
                "nda-scope-carveouts": {
                    # p2hn8sc died in the sandbox, so it is null in every key: an attempt that
                    # happened and did not pass, as opposed to one that was never measured.
                    "harbor_reward.reward": [
                        {"trial_id": "nda-scope-carveouts__p2hn8sc", "value": None},
                        {"trial_id": "nda-scope-carveouts__w5db3qy", "value": 1.0},
                        {"trial_id": "nda-scope-carveouts__z8kt1nf", "value": 0.0},
                    ],
                    "rubric_judge.criteria_pass_rate": [
                        {"trial_id": "nda-scope-carveouts__p2hn8sc", "value": None},
                        {"trial_id": "nda-scope-carveouts__w5db3qy", "value": 0.6},
                        {"trial_id": "nda-scope-carveouts__z8kt1nf", "value": 0.2},
                    ],
                },
                # Requested, but the runner returned no trial for it: keys declared, nothing measured.
                "merger-hsr-filing-threshold": {
                    "harbor_reward.reward": [],
                    "rubric_judge.criteria_pass_rate": [],
                },
            }
        ],
    )
    task_count: int = Field(default=0, description="Number of tasks represented in the run.")
    trial_count: int = Field(default=0, description="Number of distinct trials scored.")
    score_count: int = Field(default=0, description="Total number of metric scores.")

    @property
    def scores_by_name(self) -> Mapping[str, AggregateScore]:
        """Aggregates keyed by name — see :attr:`AggregatedMetricResult.scores_by_name`."""
        return self.scores.scores_by_name

    def score(self, name: str) -> AggregateScore:
        """Return the aggregate named ``name`` — see :meth:`AggregatedMetricResult.score`.

        Exists so callers needn't know the aggregates sit one level down, behind a field whose name
        differs from the summary's own accessor by a single character.
        """
        return self.scores.score(name)

    @staticmethod
    def from_scores(
        scores: Sequence[AgentEvalTaskScore],
        *,
        tasks: Sequence[AgentEvalTask] | None = None,
        extra_scores: Sequence[AggregateScore] = (),
    ) -> AgentEvalSummary:
        """Build aggregated scores, task values, and coverage for a set of metric scores.

        ``extra_scores`` are already-aggregated scores contributed by the runner (namespaced
        ``runner.<name>.``), merged in so a backend's own figures are addressable the same way as ours.
        """
        task_list = list(tasks) if tasks is not None else None
        task_metric_attempts = _task_metric_attempts(scores, task_list)
        return AgentEvalSummary(
            scores=_aggregate_scores(
                scores,
                task_list,
                extra_scores,
                task_metric_attempts=task_metric_attempts,
            ),
            metric_coverage=_metric_coverage(scores, task_list),
            task_metric_attempts=task_metric_attempts,
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


class BundleLocation(BaseModel):
    """Where a run was written, returned by :meth:`AgentEvalResult.persist`.

    Kept off :class:`AgentEvalResult` because it is not a property of the evaluation — it is the
    outcome of choosing to store it. Holding one means the bundle exists, so there is no optional to
    re-check; a run that was never persisted simply has no ``BundleLocation``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_dir: Path = Field(description="Directory the run bundle was written to.")
    dashboard_path: Path | None = Field(
        default=None,
        description="Path to the rendered HTML dashboard, or None when dashboard writing was disabled.",
    )


class AgentEvalResult(BaseModel):
    """Root result for a completed agent evaluation: tasks, trials, scores, and summary.

    Describes the evaluation and nothing else — storing it is a separate decision, made by calling
    :meth:`persist`. Because the result carries no paths, it never holds a location that was unknown
    when it was constructed, and nothing has to mutate it after the fact.
    """

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
    work_dir: Path | None = Field(
        default=None,
        description="Directory the run worked in, where its runtimes wrote trial evidence. Known "
        "before the run starts (it comes from the run config), so unlike a bundle location it is "
        "never attached after the fact. None for a purely in-memory run.",
    )

    def persist(self, output_dir: str | Path | None = None, *, write_dashboard: bool = True) -> BundleLocation:
        """Write this run to a bundle and return where it landed.

        Deliberately a call rather than something ``AgentEvaluator.run`` does for you: computing an
        evaluation and storing one are separate decisions (the same reasoning as ``publish_to_intake``).

        Defaults to :attr:`work_dir`, which is the directory the trials' evidence already lives under —
        so the bundle is self-contained and survives being moved. Passing a different ``output_dir``
        leaves those evidence references pointing back at the original directory. That is supported (a
        re-scored run may reference an earlier run's deliverables) but the resulting bundle only
        resolves while the original directory is still there.

        Set ``write_dashboard=False`` to skip rendering ``report.html``.
        """
        # Imported here rather than at module scope: persistence imports this module for the types it
        # writes, so a top-level import would be circular.
        from nemo_platform.beta.evaluator.agent_eval.persistence import persist_run

        target = output_dir if output_dir is not None else self.work_dir
        if target is None:
            raise ValueError(
                "this run has no work_dir to persist into (it ran in memory); pass an explicit "
                "output_dir, or set work_dir on the AgentEvalRunConfig so evidence and bundle share "
                "a directory"
            )
        return persist_run(self, target, write_html_dashboard=write_dashboard)

    def to_records(self, view: ResultView = "rows") -> list[dict[str, Any]]:
        """Convert this run into flat dictionaries for export or inspection.

        ``view="rows"`` yields one record per metric score — the agent-eval analogue of the dataset
        path's row. The fan-out is preserved rather than collapsed: ``task_id`` and ``trial_id`` are
        columns, so a consumer can still group by task, which is what pass@k depends on.

        ``view="aggregate"`` matches the dataset path exactly — percentiles flattened, histograms
        kept as JSON strings so the view stays tabular.

        Args:
            view: Output projection, either ``"rows"`` or ``"aggregate"``.

        Returns:
            Flat record dictionaries for downstream table/dataframe conversion.

        Raises:
            ValueError: If ``view`` is unsupported.
        """
        if view == "rows":
            return [_score_record(score) for score in self.scores]

        if view == "aggregate":
            records: list[dict[str, Any]] = []
            for score in self.summary.scores.scores:
                record: dict[str, Any] = {}
                for key, value in score.model_dump(mode="json").items():
                    if key == "percentiles" and isinstance(value, dict):
                        flatten_dict("percentiles", value, record)
                    elif key == "histogram" and value is not None:
                        # Histograms stay as JSON strings so aggregate views remain tabular instead
                        # of expanding variable-width nested columns.
                        record[key] = json.dumps(value, sort_keys=True)
                    else:
                        record[key] = value
                records.append(record)
            return records

        raise ValueError(f"Unsupported view {view!r}. Expected 'rows' or 'aggregate'.")

    def to_table(self, view: ResultView = "rows"):
        """Convert records into a ``pyarrow.Table``.

        Args:
            view: Output projection, either ``"rows"`` or ``"aggregate"``.

        Columns are unioned across every record before the table is built. ``pa.Table.from_pylist``
        takes its schema from the first record alone, and in a row view ``error`` and
        ``diagnostics.*`` appear only on failed scores — so a run whose first score succeeded would
        otherwise export a table with the failure columns silently missing. ``to_pandas`` already
        unions keys, and the two should not disagree about what a run contains.

        Args:
            view: Output projection, either ``"rows"`` or ``"aggregate"``.

        Returns:
            Table built from ``to_records(view=view)``.
        """
        import pyarrow as pa

        records = self.to_records(view=view)
        # dict-of-None preserves first-appearance order, matching how format_table derives columns.
        columns = {key: None for record in records for key in record}
        return pa.Table.from_pylist([{key: record.get(key) for key in columns} for record in records])

    def to_pandas(self, view: ResultView = "rows"):
        """Convert records into a pandas ``DataFrame``.

        Args:
            view: Output projection, either ``"rows"`` or ``"aggregate"``.

        Returns:
            DataFrame built from ``to_records(view=view)``.
        """
        import pandas as pd

        return pd.DataFrame.from_records(self.to_records(view=view))

    def format_summary(self, max_rows: int = 10, *, max_error_rows: int | None = None) -> str:
        """Render a human-readable summary with aggregates and a score preview.

        Args:
            max_rows: Maximum number of score records included in the preview.
            max_error_rows: Maximum number of failed scores included in the error-details section.
                Defaults to ``max_rows``.

        Returns:
            Multi-line summary string suitable for terminal/notebook display.
        """
        if max_error_rows is None:
            max_error_rows = max_rows
        aggregate_records = [summary_aggregate_record(score) for score in self.summary.scores.scores]
        preview = [_score_preview_record(score) for score in self.scores[:max_rows]]
        parts = [
            _agent_eval_summary_header(self),
            "",
            "Aggregate scores",
            format_table(aggregate_records),
        ]
        if preview:
            parts.extend(
                [
                    "",
                    f"Score preview (first {len(preview)} of {len(self.scores)})",
                    format_table(preview),
                ]
            )
        parts.extend(_format_score_errors(self.scores, max_error_rows=max_error_rows))
        return "\n".join(parts)

    def print_summary(self, max_rows: int = 10, *, max_error_rows: int | None = None) -> None:
        """Print ``format_summary`` output.

        Args:
            max_rows: Maximum number of score records included in the preview.
            max_error_rows: Maximum number of failed scores included in the error-details section.
                Defaults to ``max_rows``.
        """
        print(self.format_summary(max_rows=max_rows, max_error_rows=max_error_rows))

    def __str__(self) -> str:
        """Return the default compact summary representation.

        Returns:
            Summary string with up to five preview scores.
        """
        return self.format_summary(max_rows=5)


def _score_error_text(score: AgentEvalTaskScore) -> str | None:
    """Join the error-severity diagnostic messages for a score, or None when it has none."""
    messages = [
        diagnostic.message
        for diagnostic in score.diagnostics
        if diagnostic.severity is AgentEvalDiagnosticSeverity.ERROR
    ]
    return "; ".join(messages) if messages else None


def _score_diagnostics_columns(score: AgentEvalTaskScore) -> dict[str, str]:
    """JSON-encoded diagnostic columns, keyed ``diagnostics.<metric_type>``.

    Encoded as compact JSON for the same reason the dataset path does it: diagnostics have a
    metric-defined shape, and exports stay flat only if that shape is a string.
    """
    if not score.diagnostics:
        return {}
    return {
        f"diagnostics.{score.metric_type}": json.dumps(
            [serialize_value(diagnostic) for diagnostic in score.diagnostics], sort_keys=True
        )
    }


def _score_preview_record(score: AgentEvalTaskScore) -> dict[str, Any]:
    """Identity and status columns shared by the row export and the summary preview."""
    record: dict[str, Any] = {
        "task_id": score.task_id,
        "trial_id": score.trial_id,
        "metric_type": score.metric_type,
        "status": score.status.value,
    }
    for output in score.outputs:
        record[f"output.{output.name}"] = serialize_value(output.value)
    return record


def _score_record(score: AgentEvalTaskScore) -> dict[str, Any]:
    """Full export record for one score: identity, preview columns, error text, and diagnostics.

    Carries ``id``, ``run_id``, and ``metadata`` that the summary preview leaves out. An export is
    the thing a caller joins, concatenates, and keeps: ``id`` is what a row is addressable by,
    ``run_id`` keeps a frame self-describing once several runs are stacked into one, and
    ``metadata`` is caller-supplied — dropping it silently discards data the SDK never owned. The
    preview stays narrow because it is read on a terminal, the same split the dataset path makes
    between ``to_records`` and ``summary_row_base_record``.
    """
    record: dict[str, Any] = {"id": score.id, "run_id": score.run_id}
    record.update(_score_preview_record(score))
    if error_text := _score_error_text(score):
        record["error"] = error_text
    record.update(_score_diagnostics_columns(score))
    # Flattened rather than JSON-encoded: metadata is free-form but usually shallow and scalar, so
    # dotted columns keep it queryable. Diagnostics get the JSON treatment instead because their
    # shape is metric-defined and variable-width.
    flatten_dict("metadata", serialize_value(score.metadata), record)
    return record


def _agent_eval_summary_header(result: AgentEvalResult) -> str:
    """Build the header line, mirroring the shape :func:`summary_header` produces for row results.

    The counts differ because the units do — a run has tasks, trials, and scores where the dataset
    path has rows — but the ``Name(field=value, ...)`` shape is the same, and a status the run never
    produced is left out, matching what that header does with its zero counts.

    Statuses are counted by tallying the scores present, so an absent status simply never becomes a
    key; there is no zero to filter out.
    """
    status_counts: dict[str, int] = {}
    for score in result.scores:
        status_counts[score.status.value] = status_counts.get(score.status.value, 0) + 1
    fields = [
        f"tasks={len(result.tasks)}",
        f"trials={len(result.trials)}",
        f"scores={len(result.scores)}",
        f"aggregate_scores={len(result.summary.scores.scores)}",
    ]
    fields.extend(f"{status}={count}" for status, count in sorted(status_counts.items()))
    return f"AgentEvalResult({', '.join(fields)})"


def _format_score_errors(
    scores: Sequence[AgentEvalTaskScore],
    *,
    max_error_rows: int | None,
) -> list[str]:
    """Render the failed-score detail section, separating a failed trial from a failed metric.

    Both arrive as ``FAILED``, but they mean different things to a reader: a failed trial is an
    attempt the agent is answerable for, a failed metric is a measurement that never happened. The
    dataset path has no equivalent distinction to make, so this section is agent-eval's own rather
    than a reuse of :func:`format_error_details`.
    """
    failed = [score for score in scores if score.status is AgentEvalScoreStatus.FAILED]
    if not failed:
        return []

    # max(0, ...) guards a negative limit, which slicing would otherwise read as an offset from the
    # end: failed[:-2] shows all but the last two rather than none. An over-large limit needs no
    # guard, since a slice past the end is simply the whole list. Mirrors format_error_details.
    shown_limit = len(failed) if max_error_rows is None else max(0, max_error_rows)
    shown = failed[:shown_limit]
    parts = ["", f"Error details ({len(shown)} of {len(failed)} failed scores)"]
    for score in shown:
        kind = "failed trial" if is_trial_failure(score) else "failed metric"
        parts.extend(["", f"[{score.task_id} / {score.trial_id} / {score.metric_type}] {kind}"])
        parts.append(_score_error_text(score) or "(no error-severity diagnostic recorded)")
    if len(shown) < len(failed):
        parts.extend(["", f"... {len(failed) - len(shown)} more failed scores omitted"])
    return parts


def _aggregate_scores(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
    extra_scores: Sequence[AggregateScore] = (),
    *,
    task_metric_attempts: dict[str, dict[str, list[AgentEvalAttemptValue]]] | None = None,
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

    # if the caller already passed attempts → use them (no second scan of all scores)
    # if not (None) → compute them inside _aggregate_scores (no need to pass them in)
    attempts = task_metric_attempts if task_metric_attempts is not None else _task_metric_attempts(scores, tasks)
    aggregated.extend(_task_pass_at_k_scores(attempts, tasks))
    aggregated.extend(extra_scores)

    return AggregatedMetricResult(scores=aggregated)


def attempt_values(attempts: Sequence[AgentEvalAttemptValue]) -> list[float | None]:
    """The bare per-attempt values, for consumers scoring attempts without caring which trial made them.

    Preserves order, cardinality, and the None-versus-absent distinction exactly as recorded, so
    anything counting attempts (pass@k above all) reads the same sequence it would have read before
    attempts carried a trial id.
    """
    return [attempt.value for attempt in attempts]


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


def _task_metric_attempts(
    scores: Sequence[AgentEvalTaskScore],
    tasks: Sequence[AgentEvalTask] | None,
) -> dict[str, dict[str, list[AgentEvalAttemptValue]]]:
    """Ordered per-attempt records per task, keyed ``<metric_type>.<output>``.

    ``task-a`` declares ``reward.score`` (continuous), ``steps.count`` (discrete) and
    ``usage.prompt_tokens`` (a free model) and runs four trials::

        in   t0  reward 1.0        steps 5  usage 1200
             t1  reward <raised>   steps 9  usage 1300   # the judge died, not the agent
             t2  <trial died>                            # every metric fails as a trial failure
             t3  reward 0.0        steps 7  usage 1100

        out  {"task-a": {"reward.score": [(t0, 1.0), (t2, None), (t3, 0.0)],
                         "steps.count":  [(t0, 5.0), (t1, 9.0), (t2, None), (t3, 7.0)]}}

    (shown as ``(trial_id, value)`` pairs; each is an :class:`AgentEvalAttemptValue`)

    ``usage.prompt_tokens`` is absent because its declared schema is not in
    :data:`_TASK_METRIC_VALUE_SCHEMAS`; t1 is missing from ``reward.score`` but present in
    ``steps.count``; t2 is ``None`` in both.

    Which keys a task gets:

    - declared by its metric spec under :data:`_TASK_METRIC_VALUE_SCHEMAS` -> kept
    - declared under any other schema -> dropped, even when the emitted value is numeric, so a
      ``MetricOutputSpec.model("prompt_tokens", TokenCount)`` measurement never becomes a key
    - undeclared, but some score emitted a numeric value for it -> kept
    - ``tasks is None`` -> no specs to filter against, so every numeric output observed is kept

    What each score contributes to its key, in trial order:

    - failed trial (:func:`is_trial_failure`) -> value ``None``, an attempt that did not pass
    - failed metric, or the output absent -> no entry; the attempt is unmeasured, not unsuccessful
    - otherwise -> the numeric value

    pass@k needs that asymmetry, and it is why a list is indexed by surviving measurement rather than
    by attempt: above, index 1 is t2 under ``reward.score`` but t1 under ``steps.count``. Every entry
    therefore names its trial, and ``trial_id`` — not position — is what joins two keys of one task,
    or joins out to ``trials.jsonl`` and ``scores.jsonl``. Ids are recorded as the runner reported
    them and are never deduplicated: two attempts sharing an id stay two attempts, so a runner that
    reuses one costs pass@k nothing.
    """
    output_keys: dict[str, set[tuple[str, str]]] = {}
    # Declared under a schema this mapping does not retain. Tracked so an emitted numeric value cannot
    # add back what the spec filter just excluded.
    excluded: set[tuple[str, str]] = set()
    if tasks is not None:
        for task in tasks:
            task_keys = output_keys.setdefault(task.id, set())
            for metric in task.metrics:
                metric_type = metric_type_name(metric)
                for spec in metric.output_spec():
                    if issubclass(spec.value_schema, _TASK_METRIC_VALUE_SCHEMAS):
                        task_keys.add((metric_type, spec.name))
                    else:
                        excluded.add((metric_type, spec.name))

    scores_by_task_metric: dict[tuple[str, str], list[AgentEvalTaskScore]] = {}
    for score in scores:
        scores_by_task_metric.setdefault((score.task_id, score.metric_type), []).append(score)
        task_keys = output_keys.setdefault(score.task_id, set())
        if score.status not in (AgentEvalScoreStatus.COMPLETED, AgentEvalScoreStatus.PARTIAL):
            continue
        for output in score.outputs:
            if (score.metric_type, output.name) in excluded:
                continue
            if _semantic_value(output) is not None:
                task_keys.add((score.metric_type, output.name))

    by_task: dict[str, dict[str, list[AgentEvalAttemptValue]]] = {}
    for task_id, keys in output_keys.items():
        task_values: dict[str, list[AgentEvalAttemptValue]] = {}
        for metric_type, output_name in sorted(keys):
            values: list[AgentEvalAttemptValue] = []
            for score in scores_by_task_metric.get((task_id, metric_type), []):
                if is_trial_failure(score):
                    values.append(AgentEvalAttemptValue(trial_id=score.trial_id, value=None))
                    continue
                if score.status not in (AgentEvalScoreStatus.COMPLETED, AgentEvalScoreStatus.PARTIAL):
                    continue
                output = _score_output(score, output_name)
                value = _semantic_value(output) if output is not None else None
                if value is not None:
                    values.append(AgentEvalAttemptValue(trial_id=score.trial_id, value=value))
            task_values[f"{metric_type}.{output_name}"] = values
        by_task[task_id] = task_values
    return by_task


def _task_pass_at_k_scores(
    task_metric_attempts: dict[str, dict[str, list[AgentEvalAttemptValue]]],
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

    "No usable attempt" includes a task that was never scored at all: a runner that returns no trial
    for a requested task (Harbor logs a warning and carries on) leaves it declaring the metric with an
    empty attempt list, and it lands in ``nan_count`` like any other unmeasured task. That is
    deliberate — it is the same missing coverage whether the trial died or was never produced, and
    excluding it would report pass@k over a denominator quietly smaller than the task set asked for.
    """
    scorelike = _scorelike_outputs(tasks)
    if not scorelike:
        return []
    aggregated: list[AggregateScore] = []
    for metric_type, output_name in sorted(scorelike):
        key = f"{metric_type}.{output_name}"
        values_by_task = [attempt_values(outputs[key]) for outputs in task_metric_attempts.values() if key in outputs]
        measured = [values for values in values_by_task if values]
        if not measured:
            continue
        # Empty attempt lists stay in nan_count (via total); for each k, mean the unbiased
        # estimator over tasks with n >= k (None / < full credit do not count as passes).
        unmeasured = sum(not values for values in values_by_task)
        max_n = max(len(values) for values in measured)
        for k in range(1, max_n + 1):
            per_task = [
                _pass_at_k(
                    len(values),
                    sum(value is not None and value >= _PASS_VALUE for value in values),
                    k,
                )
                for values in measured
                if len(values) >= k
            ]
            if per_task:
                aggregated.append(_aggregate_range_score(f"{key}.pass@{k}", per_task, len(per_task) + unmeasured))
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
