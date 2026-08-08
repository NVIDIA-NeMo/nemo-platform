# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Adapt a dataset-driven (row) evaluation result into the shape ``publish_to_intake`` consumes.

Row evaluation and agent evaluation converge at the Intake boundary: a published trajectory is a
single step carrying the final output text (see ``mapping.trial_to_atif_ingest``), and a row's
``sample`` is already ``{"output_text": ..., "response": ...}`` — the field names of ``AgentOutput``.
So rather than a second mapping and a second publish loop, a row result is adapted to an
``AgentEvalResult`` and goes through the same publisher, inheriting its idempotency guarantees.

The row vocabulary maps as: one row -> one trial, one (row, metric key) -> one score. A row's
test case identity is its content hash by default, so repeated rows become repeated trials of a
single test case — which is what the trial/task split already expresses.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary, RunMetadata
from nemo_evaluator_sdk.agent_eval.scores import (
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.values.dataset_schemas import _KNOWN_BINDING_FIELDS
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import EvaluationResult, RowScore

#: Key ``sample`` carries when generation itself failed, rather than the metric.
_INFERENCE_ERROR = "inference_error"

#: Canonical evaluator fields that ``field_mapping`` copies into a row alongside its own columns.
_CANONICAL_FIELDS = frozenset(_KNOWN_BINDING_FIELDS)


class RowIdentityError(ValueError):
    """A row's published identity is unusable — missing, or shared with another row."""


def _canonical_row_hash(row: RowScore) -> str:
    """Stable ``sha256`` of a row's dataset content, excluding field-mapping's canonical aliases.

    Mirrors ``gym_runtime._canonical_row_hash``: identity is the row content alone, so a row keeps
    its id across dataset revisions and reorderings and a changed row becomes a new test case. The
    aliases are excluded because they duplicate values already in the row, so hashing them would
    change the id whenever only the ``field_mapping`` changed.
    """
    payload = {key: value for key, value in row.item.items() if key not in _CANONICAL_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _task_id(row: RowScore, index: int, test_case_id_field: str | None) -> str:
    """The row's test case identity — stable run over run, so rollups line up."""
    if test_case_id_field is None:
        return _canonical_row_hash(row)
    if test_case_id_field not in row.item:
        raise RowIdentityError(
            f"Row {index} has no {test_case_id_field!r} column; "
            f"available columns: {sorted(row.item)}. "
            "Fix `publication.intake.test_case_id_field` or remove it to identify rows by content."
        )
    return str(row.item[test_case_id_field])


def _output(row: RowScore) -> AgentOutput | None:
    """The row's generated output, or ``None`` when generation failed or produced nothing."""
    if row.sample.get(_INFERENCE_ERROR):
        return None
    output_text = row.sample.get("output_text")
    response = row.sample.get("response")
    if output_text is None and not response:
        return None
    return AgentOutput(output_text=output_text, response=response)


def _scores(row: RowScore, *, run_id: str, task_id: str, trial_id: str) -> list[AgentEvalTaskScore]:
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
                id=f"{run_id}:{trial_id}:{metric_key}",
                run_id=run_id,
                task_id=task_id,
                trial_id=trial_id,
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
    first_seen: dict[str, int] = {}
    occurrences: dict[str, int] = {}
    for index, row in enumerate(result.row_scores):
        task_id = _task_id(row, index, test_case_id_field)
        repeat = occurrences.get(task_id, 0)
        # A named column that repeats is a misconfiguration — the submitter said it identifies rows.
        # Identical content under the content hash is just the same test case evaluated twice.
        if repeat and test_case_id_field is not None:
            raise RowIdentityError(
                f"Rows {first_seen[task_id]} and {index} share test case id {task_id!r} from column "
                f"{test_case_id_field!r}. Name a column whose values are unique per row."
            )
        occurrences[task_id] = repeat + 1
        first_seen.setdefault(task_id, index)
        # Session ids are `{run_id}:{trial id}`, so repeats need distinct trial ids or the second
        # trajectory would replace the first. They keep one `task_id`, which is what rollups group on.
        trial_id = task_id if repeat == 0 else f"{task_id}#{repeat + 1}"
        output = _output(row)
        trials.append(
            AgentEvalTrial(
                id=trial_id,
                task_id=task_id,
                status=AgentEvalTrialStatus.COMPLETED if output is not None else AgentEvalTrialStatus.FAILED,
                output=output,
            )
        )
        scores.extend(_scores(row, run_id=run_id, task_id=task_id, trial_id=trial_id))

    return AgentEvalResult(
        run_id=run_id,
        tasks=[],
        trials=trials,
        scores=scores,
        summary=AgentEvalSummary(scores=result.aggregate_scores),
        metadata=RunMetadata(started_at=started_at),
    )
