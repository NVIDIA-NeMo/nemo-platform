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


def test_identity_defaults_to_a_content_hash() -> None:
    result = _adapt([_row(item={"qid": "a"}), _row(item={"qid": "b"})])
    ids = [trial.task_id for trial in result.trials]
    assert ids[0] != ids[1]
    assert all(len(i) == 64 for i in ids)


def test_identity_ignores_row_position() -> None:
    # The whole point of hashing: a reordered or renumbered dataset keeps its ids.
    first = _adapt([_row(row_index=0, item={"qid": "a"}), _row(row_index=1, item={"qid": "b"})])
    reordered = _adapt([_row(row_index=7, item={"qid": "b"}), _row(row_index=9, item={"qid": "a"})])
    assert {t.task_id for t in first.trials} == {t.task_id for t in reordered.trials}


def test_identity_ignores_field_mapping_aliases() -> None:
    # `field_mapping` copies columns into canonical keys on `item`; hashing them would churn ids
    # whenever only the mapping changed.
    bare = _adapt([_row(item={"question": "2+2?"})])
    mapped = _adapt([_row(item={"question": "2+2?", "input": "2+2?", "reference": "4"})])
    assert bare.trials[0].task_id == mapped.trials[0].task_id


def test_changed_content_becomes_a_new_test_case() -> None:
    before = _adapt([_row(item={"question": "2+2?"})])
    after = _adapt([_row(item={"question": "3+3?"})])
    assert before.trials[0].task_id != after.trials[0].task_id


def test_test_case_id_field_overrides_the_hash() -> None:
    result = _adapt(
        [_row(item={"qid": "q-42"}), _row(row_index=1, item={"qid": "q-7"})],
        test_case_id_field="qid",
    )
    assert [trial.id for trial in result.trials] == ["q-42", "q-7"]


def test_non_string_id_column_is_coerced() -> None:
    result = _adapt([_row(item={"qid": 42})], test_case_id_field="qid")
    assert result.trials[0].id == "42"


def test_duplicate_id_column_values_are_rejected() -> None:
    # A named column that repeats is a misconfiguration: the submitter said it identifies rows.
    with pytest.raises(RowIdentityError, match="share test case id 'q-1'"):
        _adapt([_row(item={"qid": "q-1"}), _row(row_index=1, item={"qid": "q-1"})], test_case_id_field="qid")


def test_identical_rows_are_trials_of_one_test_case() -> None:
    # Repeated rows are the same test case evaluated twice, which the model already expresses as
    # N trials per task. Distinct trial ids keep their sessions apart; the shared task_id groups them.
    result = _adapt([_row(item={"qid": "a"}), _row(row_index=1, item={"qid": "a"})])
    task_ids = [trial.task_id for trial in result.trials]
    trial_ids = [trial.id for trial in result.trials]
    assert task_ids[0] == task_ids[1]
    assert trial_ids[0] != trial_ids[1]
    assert trial_ids[1] == f"{task_ids[0]}#2"
    assert [score.trial_id for score in result.scores] == trial_ids
    assert len({score.id for score in result.scores}) == 2


def test_missing_id_column_raises_instead_of_falling_back() -> None:
    # Falling back to the hash would silently ignore an explicit request and give no indication why
    # the expected ids never appeared.
    with pytest.raises(RowIdentityError, match="no 'qid' column"):
        _adapt([_row(item={"question": "2+2?"})], test_case_id_field="qid")


# --- failures ---------------------------------------------------------------


def test_inference_failure_becomes_a_failed_trial() -> None:
    result = _adapt([_row(sample={"output_text": None, "response": {}, "inference_error": "boom"})])
    assert result.trials[0].status == AgentEvalTrialStatus.FAILED
    assert result.trials[0].output is None


def test_empty_sample_becomes_a_failed_trial() -> None:
    # The generation path omits `output_text`/`response` entirely when falsy, so a row that produced
    # nothing carries neither key.
    result = _adapt([_row(sample={})])
    assert result.trials[0].status == AgentEvalTrialStatus.FAILED
    assert result.trials[0].output is None


@pytest.mark.parametrize("response", [False, 0, [], {}])
def test_falsy_response_is_still_an_output(response: object) -> None:
    # `AgentOutput.response` is any JSON value, so a falsy one is data, not absence — publishing it
    # as a failed trial would drop a completed row's output.
    result = _adapt([_row(sample={"output_text": None, "response": response})])
    assert result.trials[0].status == AgentEvalTrialStatus.COMPLETED
    assert result.trials[0].output is not None
    assert result.trials[0].output.response == response


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


# --- token usage ------------------------------------------------------------


def _usage_metadata(usage: object) -> dict[str, Any]:
    return _adapt([_row(sample={"output_text": "4", "response": {"usage": usage}})]).trials[0].metadata


def test_openai_usage_becomes_trial_token_measurements() -> None:
    # Publishing reads these keys off trial metadata, so the names are the contract with
    # TrialMeasurements.from_metadata; total_tokens is deliberately absent (Intake recomputes it).
    metadata = _usage_metadata(
        {
            "prompt_tokens": 22635,
            "completion_tokens": 2949,
            "total_tokens": 25584,
            "prompt_tokens_details": {"cached_tokens": 1200},
        }
    )
    assert metadata == {"prompt_tokens": 22635, "completion_tokens": 2949, "cache_read_tokens": 1200}


def test_anthropic_usage_is_read_under_its_own_key_names() -> None:
    # A GenericAgent can target any endpoint, so an Anthropic-shaped block must not be dropped whole.
    metadata = _usage_metadata(
        {
            "input_tokens": 358,
            "output_tokens": 19324,
            "cache_read_input_tokens": 3984621,
            "cache_creation_input_tokens": 512,
        }
    )
    assert metadata == {
        "prompt_tokens": 358,
        "completion_tokens": 19324,
        "cache_read_tokens": 3984621,
        "cache_creation_tokens": 512,
    }


def test_openai_keys_win_when_a_response_carries_both_schemas() -> None:
    metadata = _usage_metadata({"prompt_tokens": 10, "input_tokens": 999, "completion_tokens": 20})
    assert metadata["prompt_tokens"] == 10


@pytest.mark.parametrize("usage", [None, {}, "1000", {"prompt_tokens": None}, {"prompt_tokens": "22635"}])
def test_unusable_usage_records_no_tokens(usage: object) -> None:
    # A missing count must stay missing rather than land as a wrong number.
    assert _usage_metadata(usage) == {}


def test_zero_counts_are_recorded_rather_than_dropped() -> None:
    # NAT reports prompt_tokens=0; 0 is a reported measurement and must survive a truthiness filter.
    assert _usage_metadata({"prompt_tokens": 0, "completion_tokens": 38}) == {
        "prompt_tokens": 0,
        "completion_tokens": 38,
    }


def test_booleans_are_not_counted_as_token_counts() -> None:
    assert _usage_metadata({"prompt_tokens": True, "completion_tokens": 38}) == {"completion_tokens": 38}


def test_a_row_without_a_response_records_no_tokens() -> None:
    assert _adapt([_row(sample={"output_text": "4"})]).trials[0].metadata == {}
