# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapt a dataset-driven (row) evaluation result into the shape ``publish_to_intake`` consumes.

Row evaluation and agent evaluation converge at the Intake boundary: a published trajectory is a
single step carrying the final output text (see ``mapping.trial_to_atif_ingest``), and a row's
``sample`` is already ``{"output_text": ..., "response": ...}`` — the field names of ``AgentOutput``.
So rather than a second mapping and a second publish loop, a row result is adapted to an
``AgentEvalResult`` and goes through the same publisher, inheriting its idempotency guarantees.

The row vocabulary maps as: one row -> one trial, one (row, metric key) -> one score.
"""

from __future__ import annotations

from datetime import datetime

from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary, RunMetadata
from nemo_evaluator_sdk.agent_eval.scores import (
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import EvaluationResult, RowScore

#: Key ``sample`` carries when generation itself failed, rather than the metric.
_INFERENCE_ERROR = "inference_error"


class RowIdentityError(ValueError):
    """A row's published identity is unusable — missing, or shared with another row."""


def _test_case_id(row: RowScore, index: int, test_case_id_field: str | None) -> str:
    """Stable identity for a row, used as both trial id and published test case id."""
    if test_case_id_field is not None:
        # Deliberately not falling back to the positional id: the whole point of naming a column is
        # that positions are not stable, so a silent fallback would publish rows that never line up
        # with the previous run and give no indication of why.
        if test_case_id_field not in row.item:
            raise RowIdentityError(
                f"Row {index} has no {test_case_id_field!r} column; "
                f"available columns: {sorted(row.item)}. "
                "Fix `publication.intake.test_case_id_field` or remove it to use row position."
            )
        return str(row.item[test_case_id_field])
    return f"row-{row.row_index if row.row_index is not None else index}"


def _output(row: RowScore) -> AgentOutput | None:
    """The row's generated output, or ``None`` when generation failed or produced nothing."""
    if row.sample.get(_INFERENCE_ERROR):
        return None
    output_text = row.sample.get("output_text")
    response = row.sample.get("response")
    if output_text is None and not response:
        return None
    return AgentOutput(output_text=output_text, response=response)


def _scores(row: RowScore, *, run_id: str, test_case_id: str) -> list[AgentEvalTaskScore]:
    """One score per metric key on the row; ``metrics`` values are already ``MetricOutput``."""
    errors = row.metric_errors or {}
    diagnostics = row.metric_diagnostics or {}
    scores: list[AgentEvalTaskScore] = []
    for metric_key, outputs in row.metrics.items():
        error = errors.get(metric_key)
        # Error first: `score_to_evaluator_results` publishes `diagnostics[0].message` as the row's
        # comment, and the failure is what a reader needs to see there.
        row_diagnostics = [
            AgentEvalDiagnostic(severity=AgentEvalDiagnosticSeverity.WARNING, message=item.message)
            for item in diagnostics.get(metric_key, [])
        ]
        if error:
            row_diagnostics.insert(0, AgentEvalDiagnostic(severity=AgentEvalDiagnosticSeverity.ERROR, message=error))
        scores.append(
            AgentEvalTaskScore(
                id=f"{run_id}:{test_case_id}:{metric_key}",
                run_id=run_id,
                task_id=test_case_id,
                trial_id=test_case_id,
                metric_type=metric_key,
                status=AgentEvalScoreStatus.FAILED if error else AgentEvalScoreStatus.COMPLETED,
                outputs=list(outputs),
                diagnostics=row_diagnostics,
            )
        )
    return scores


def row_result_to_agent_eval_result(
    result: EvaluationResult | BenchmarkEvaluationResult,
    *,
    run_id: str,
    started_at: datetime,
    test_case_id_field: str | None = None,
) -> AgentEvalResult:
    """Adapt a row evaluation result for ``publish_to_intake``.

    ``run_id`` and ``started_at`` come from the job: a row result carries neither, and both must be
    stable across a re-publish or the trajectory lands as a duplicate span rather than replacing the
    previous one.

    Reads the top-level ``row_scores`` only. ``BenchmarkEvaluationResult`` repeats every row under
    ``per_metric[key].row_scores`` as well; walking those would publish each row once per metric.
    """
    trials: list[AgentEvalTrial] = []
    scores: list[AgentEvalTaskScore] = []
    # Published session ids are `{run_id}:{trial id}`, so two rows sharing an id are one session:
    # the second trajectory replaces the first and its scores land on the same span. That loses a row
    # with nothing to show for it, so refuse the whole run instead — a column that is not unique is a
    # misconfiguration, and publishing 1 of 1000 rows silently is the worst way to find out.
    seen: dict[str, int] = {}
    for index, row in enumerate(result.row_scores):
        test_case_id = _test_case_id(row, index, test_case_id_field)
        if test_case_id in seen:
            source = (
                f"column {test_case_id_field!r}"
                if test_case_id_field is not None
                else "row position (rows carry inconsistent `row_index` values)"
            )
            raise RowIdentityError(
                f"Rows {seen[test_case_id]} and {index} both resolve to test case id "
                f"{test_case_id!r} from {source}. Ids must be unique or the rows overwrite each "
                "other in Intake."
            )
        seen[test_case_id] = index
        output = _output(row)
        trials.append(
            AgentEvalTrial(
                id=test_case_id,
                task_id=test_case_id,
                status=AgentEvalTrialStatus.COMPLETED if output is not None else AgentEvalTrialStatus.FAILED,
                output=output,
            )
        )
        scores.extend(_scores(row, run_id=run_id, test_case_id=test_case_id))

    return AgentEvalResult(
        run_id=run_id,
        tasks=[],
        trials=trials,
        scores=scores,
        summary=AgentEvalSummary(scores=result.aggregate_scores),
        metadata=RunMetadata(started_at=started_at),
    )
