# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for adapting a dataset-driven eval result into the publisher's shape."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from nemo_evaluator.intake.row_adapter import RowIdentityError, row_result_to_agent_eval_result
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus
from nemo_evaluator_sdk.metrics.protocol import MetricOutput
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, EvaluationResult, RowScore

RUN_ID = "job-1"
STARTED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _row(
    *,
    row_index: int | None = 0,
    item: dict[str, Any] | None = None,
    sample: dict[str, Any] | None = None,
    metrics: dict[str, list[MetricOutput]] | None = None,
    metric_errors: dict[str, str] | None = None,
    metric_diagnostics: dict[str, list[Any]] | None = None,
) -> RowScore:
    return RowScore(
        row_index=row_index,
        item=item if item is not None else {"question": "2+2?"},
        sample=sample if sample is not None else {"output_text": "4", "response": {"choices": []}},
        metrics=metrics if metrics is not None else {"exact_match": [MetricOutput(name="score", value=1.0)]},
        requests=[],
        metric_errors=metric_errors,
        metric_diagnostics=metric_diagnostics,
    )


def _result(rows: list[RowScore]) -> EvaluationResult:
    return EvaluationResult(row_scores=rows, aggregate_scores=AggregatedMetricResult(scores=[]))


def _adapt(rows: list[RowScore], **kwargs: Any) -> Any:
    return row_result_to_agent_eval_result(_result(rows), run_id=RUN_ID, started_at=STARTED_AT, **kwargs)


# --- shape ------------------------------------------------------------------


def test_row_becomes_a_trial_carrying_its_sample() -> None:
    result = _adapt([_row()])

    assert result.run_id == RUN_ID
    assert result.metadata.started_at == STARTED_AT
    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.status == AgentEvalTrialStatus.COMPLETED
    assert trial.output is not None
    assert trial.output.output_text == "4"
    assert trial.output.response == {"choices": []}


def test_each_metric_key_becomes_its_own_score() -> None:
    result = _adapt(
        [
            _row(
                metrics={
                    "exact_match": [MetricOutput(name="score", value=1.0)],
                    "judge": [MetricOutput(name="verdict", value="correct")],
                }
            )
        ]
    )

    assert {score.metric_type for score in result.scores} == {"exact_match", "judge"}
    assert all(score.trial_id == result.trials[0].id for score in result.scores)
    assert all(score.run_id == RUN_ID for score in result.scores)
    # Score ids must be distinct or Intake would collapse them onto one row.
    assert len({score.id for score in result.scores}) == 2


def test_aggregate_scores_carry_into_the_summary() -> None:
    aggregates = AggregatedMetricResult(scores=[])
    result = row_result_to_agent_eval_result(
        EvaluationResult(row_scores=[_row()], aggregate_scores=aggregates),
        run_id=RUN_ID,
        started_at=STARTED_AT,
    )
    assert result.summary.scores == aggregates


def test_benchmark_result_rows_are_not_published_once_per_metric() -> None:
    # BenchmarkEvaluationResult repeats every row under per_metric; only the top-level list counts.
    row = _row()
    single = _result([row])
    result = row_result_to_agent_eval_result(
        BenchmarkEvaluationResult(
            row_scores=[row],
            aggregate_scores=AggregatedMetricResult(scores=[]),
            per_metric={"exact_match": single, "judge": single},
        ),
        run_id=RUN_ID,
        started_at=STARTED_AT,
    )
    assert len(result.trials) == 1


# --- identity ---------------------------------------------------------------


def test_defaults_to_row_position() -> None:
    result = _adapt([_row(row_index=0), _row(row_index=1)])
    assert [trial.id for trial in result.trials] == ["row-0", "row-1"]
    assert [trial.task_id for trial in result.trials] == ["row-0", "row-1"]


def test_falls_back_to_enumeration_when_row_index_is_absent() -> None:
    result = _adapt([_row(row_index=None), _row(row_index=None)])
    assert [trial.id for trial in result.trials] == ["row-0", "row-1"]


def test_test_case_id_field_overrides_position() -> None:
    result = _adapt(
        [_row(item={"qid": "q-42"}), _row(row_index=1, item={"qid": "q-7"})],
        test_case_id_field="qid",
    )
    assert [trial.id for trial in result.trials] == ["q-42", "q-7"]


def test_non_string_id_column_is_coerced() -> None:
    result = _adapt([_row(item={"qid": 42})], test_case_id_field="qid")
    assert result.trials[0].id == "42"


def test_missing_id_column_raises_instead_of_falling_back() -> None:
    # A silent fallback to row position would reinstate exactly the instability the field exists to
    # remove, and the caller would have no way to notice.
    with pytest.raises(RowIdentityError, match="no 'qid' column"):
        _adapt([_row(item={"question": "2+2?"})], test_case_id_field="qid")


# --- failures ---------------------------------------------------------------


def test_inference_failure_becomes_a_failed_trial() -> None:
    result = _adapt([_row(sample={"output_text": None, "response": {}, "inference_error": "boom"})])
    assert result.trials[0].status == AgentEvalTrialStatus.FAILED
    assert result.trials[0].output is None


def test_empty_sample_becomes_a_failed_trial() -> None:
    result = _adapt([_row(sample={"output_text": None, "response": {}})])
    assert result.trials[0].status == AgentEvalTrialStatus.FAILED


def test_metric_error_becomes_a_failed_score_reporting_why() -> None:
    result = _adapt([_row(metric_errors={"exact_match": "judge timed out"})])
    score = result.scores[0]
    assert score.status == AgentEvalScoreStatus.FAILED
    # Publish surfaces diagnostics[0].message as the row comment, so the error must lead.
    assert score.diagnostics[0].message == "judge timed out"


def test_a_metric_error_does_not_fail_the_trial_itself() -> None:
    # The agent answered; only scoring failed. The trajectory is still worth publishing.
    result = _adapt([_row(metric_errors={"exact_match": "judge timed out"})])
    assert result.trials[0].status == AgentEvalTrialStatus.COMPLETED
