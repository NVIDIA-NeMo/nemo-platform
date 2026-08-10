# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Display and export surface on AgentEvalResult, mirroring the dataset path's."""

from __future__ import annotations

import pytest
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import (
    TRIAL_STATUS_DETAIL,
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus
from nemo_evaluator_sdk.values.protocol import MetricOutput

_TRIAL_FAILURE = AgentEvalDiagnostic(
    severity=AgentEvalDiagnosticSeverity.ERROR,
    message="agent crashed",
    details={TRIAL_STATUS_DETAIL: AgentEvalTrialStatus.FAILED.value},
)
_METRIC_FAILURE = AgentEvalDiagnostic(
    severity=AgentEvalDiagnosticSeverity.ERROR,
    message="judge timed out",
    details={"exception_type": "TimeoutError"},
)


def _score(
    task_id: str,
    trial_id: str,
    value: float | None = None,
    *,
    status: AgentEvalScoreStatus = AgentEvalScoreStatus.COMPLETED,
    diagnostics: tuple[AgentEvalDiagnostic, ...] = (),
) -> AgentEvalTaskScore:
    return AgentEvalTaskScore(
        id=f"{task_id}-{trial_id}",
        run_id="run-1",
        task_id=task_id,
        trial_id=trial_id,
        metric_type="reward",
        status=status,
        outputs=[MetricOutput(name="reward", value=value)] if value is not None else [],
        diagnostics=list(diagnostics),
    )


def _result(*scores: AgentEvalTaskScore) -> AgentEvalResult:
    return AgentEvalResult(
        run_id="run-1",
        tasks=[],
        trials=[],
        scores=list(scores),
        summary=AgentEvalSummary.from_scores(scores),
    )


def _passing_run() -> AgentEvalResult:
    return _result(_score("t1", "a", 1.0), _score("t1", "b", 0.0), _score("t2", "a", 1.0))


def _run_with_failures() -> AgentEvalResult:
    return _result(
        _score("t1", "a", 1.0),
        _score("t2", "b", status=AgentEvalScoreStatus.FAILED, diagnostics=(_TRIAL_FAILURE,)),
        _score("t3", "a", status=AgentEvalScoreStatus.FAILED, diagnostics=(_METRIC_FAILURE,)),
    )


def test_row_records_keep_the_task_grouping_that_pass_at_k_depends_on() -> None:
    # The fan-out is load-bearing: flattening trials into anonymous rows would make it impossible to
    # regroup by task, so task_id and trial_id have to survive as columns.
    records = _passing_run().to_records()

    assert [record["task_id"] for record in records] == ["t1", "t1", "t2"]
    assert [record["trial_id"] for record in records] == ["a", "b", "a"]
    assert records[0]["output.reward"] == 1.0


def test_row_records_carry_error_text_and_diagnostics_only_for_failures() -> None:
    records = _run_with_failures().to_records()

    assert "error" not in records[0]
    assert records[1]["error"] == "agent crashed"
    assert "diagnostics.reward" in records[1]


def test_aggregate_view_flattens_percentiles_like_the_dataset_path() -> None:
    records = _passing_run().to_records(view="aggregate")

    assert records[0]["name"] == "reward.reward"
    # Percentiles are flattened into columns rather than left nested, so the view stays tabular.
    assert "percentiles.p50" in records[0]
    assert "percentiles" not in records[0]


def test_unsupported_view_is_rejected_with_the_same_message_as_the_dataset_path() -> None:
    with pytest.raises(ValueError, match=r"Unsupported view 'nope'. Expected 'rows' or 'aggregate'."):
        _passing_run().to_records(view="nope")  # ty: ignore[invalid-argument-type]


def test_to_table_keeps_columns_that_only_appear_on_later_records() -> None:
    # pa.Table.from_pylist takes its schema from the first record. Error and diagnostics columns
    # appear only on failures, so a run whose first score passed would silently export without them.
    table = _run_with_failures().to_table()

    assert "error" in table.column_names
    assert "diagnostics.reward" in table.column_names


def test_to_table_and_to_pandas_agree_on_columns() -> None:
    result = _run_with_failures()

    assert set(result.to_table().column_names) == set(result.to_pandas().columns)


def test_to_table_handles_a_run_with_no_scores() -> None:
    assert _result().to_table().num_rows == 0


def test_summary_header_reports_the_units_a_run_actually_has() -> None:
    header = _run_with_failures().format_summary().splitlines()[0]

    assert header.startswith("AgentEvalResult(")
    assert "scores=3" in header
    assert "completed=1" in header
    assert "failed=2" in header


def test_summary_header_lists_only_the_statuses_the_run_produced() -> None:
    # Matches the dataset path's header, which leaves out statuses with nothing behind them.
    header = _passing_run().format_summary().splitlines()[0]

    assert "completed=3" in header
    assert "failed" not in header
    assert "partial" not in header


def test_summary_separates_a_failed_trial_from_a_failed_metric() -> None:
    # Both surface as FAILED but mean different things: a failed trial is an attempt the agent is
    # answerable for, a failed metric is a measurement that never happened. Each label is asserted
    # against the score it describes -- checking only that both strings appear would still pass if
    # the two were swapped.
    summary = _run_with_failures().format_summary()

    assert "[t2 / b / reward] failed trial\nagent crashed" in summary
    assert "[t3 / a / reward] failed metric\njudge timed out" in summary


def test_summary_has_no_error_section_when_nothing_failed() -> None:
    assert "Error details" not in _passing_run().format_summary()


def test_summary_preview_is_capped_and_says_what_it_is_showing() -> None:
    result = _result(*(_score(f"t{index}", "a", 1.0) for index in range(8)))

    summary = result.format_summary(max_rows=3)

    assert "Score preview (first 3 of 8)" in summary
    assert "t7" not in summary


def test_error_section_reports_how_many_failures_it_omitted() -> None:
    result = _result(
        *(
            _score(f"t{index}", "a", status=AgentEvalScoreStatus.FAILED, diagnostics=(_METRIC_FAILURE,))
            for index in range(5)
        )
    )

    summary = result.format_summary(max_error_rows=2)

    assert "Error details (2 of 5 failed scores)" in summary
    assert "3 more failed scores omitted" in summary


def test_max_error_rows_follows_max_rows_when_not_given() -> None:
    # The documented default. Without this, tightening the preview would silently leave the error
    # section at its own limit, and the two sections would disagree about how much they are showing.
    result = _result(
        *(
            _score(f"t{index}", "a", status=AgentEvalScoreStatus.FAILED, diagnostics=(_METRIC_FAILURE,))
            for index in range(3)
        )
    )

    assert "Error details (1 of 3 failed scores)" in result.format_summary(max_rows=1)


def test_str_renders_the_compact_summary_capped_at_five_rows() -> None:
    # Matches EvaluationResult.__str__, which previews five rows.
    result = _result(*(_score(f"t{index}", "a", 1.0) for index in range(8)))

    rendered = str(result)

    assert rendered.startswith("AgentEvalResult(")
    assert "Score preview (first 5 of 8)" in rendered


def test_print_summary_writes_format_summary_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    result = _passing_run()

    result.print_summary()

    assert capsys.readouterr().out == f"{result.format_summary()}\n"
