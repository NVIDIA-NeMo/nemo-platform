# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Evaluator -> Intake boundary mapping module."""

from __future__ import annotations

import pytest
from nemo_evaluator.intake.mapping import (
    ATIF_SCHEMA_VERSION,
    DEFAULT_AGENT_VERSION,
    run_task_to_experiment_context,
    score_to_evaluator_results,
    session_id_for,
    trial_to_atif_ingest,
)
from nemo_evaluator_sdk.agent_eval.scores import (
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.metrics.protocol import (
    BooleanValue,
    ContinuousScore,
    DiscreteScore,
    Label,
    MetricOutput,
)


def _trial(*, trial_id: str = "trial-1", task_id: str = "task-1", output_text: str | None = "hello") -> AgentEvalTrial:
    output = AgentOutput(output_text=output_text) if output_text is not None else None
    status = AgentEvalTrialStatus.COMPLETED if output is not None else AgentEvalTrialStatus.FAILED
    return AgentEvalTrial(id=trial_id, task_id=task_id, status=status, output=output)


def _score(*, outputs: list[MetricOutput], diagnostics: list[AgentEvalDiagnostic] | None = None) -> AgentEvalTaskScore:
    return AgentEvalTaskScore(
        id="score-1",
        run_id="run-1",
        task_id="task-1",
        trial_id="trial-1",
        metric_type="accuracy",
        status=AgentEvalScoreStatus.COMPLETED,
        outputs=outputs,
        diagnostics=diagnostics or [],
    )


# --- session_id_for ---------------------------------------------------------


def test_session_id_is_stable_per_trial() -> None:
    assert session_id_for("run-1", "trial-1") == "run-1:trial-1"


# --- run_task_to_experiment_context -----------------------------------------


def test_experiment_context_is_lean() -> None:
    context = run_task_to_experiment_context(_trial(task_id="task-42"), experiment_id="bench-x-variant")
    assert context == {"experiment_id": "bench-x-variant", "test_case_id": "task-42"}


# --- trial_to_atif_ingest ---------------------------------------------------


def test_trial_to_atif_ingest_shape() -> None:
    body = trial_to_atif_ingest(
        _trial(trial_id="t-1", task_id="task-1", output_text="final answer"),
        run_id="run-1",
        experiment_id="exp-1",
        agent_name="my-agent",
        model_name="gpt-4o",
    )
    assert body["schema_version"] == ATIF_SCHEMA_VERSION
    assert body["session_id"] == "run-1:t-1"
    assert body["agent"] == {"name": "my-agent", "version": DEFAULT_AGENT_VERSION, "model_name": "gpt-4o"}
    assert body["steps"] == [{"source": "agent", "step_id": 1, "message": "final answer"}]
    assert body["experiment_context"] == {"experiment_id": "exp-1", "test_case_id": "task-1"}
    assert "final_metrics" not in body


def test_trial_to_atif_ingest_defaults_version_and_omits_model_name() -> None:
    body = trial_to_atif_ingest(_trial(), run_id="run-1", experiment_id="exp-1", agent_name="a")
    assert body["agent"] == {"name": "a", "version": "unknown"}
    assert "model_name" not in body["agent"]


def test_trial_to_atif_ingest_handles_missing_output() -> None:
    body = trial_to_atif_ingest(_trial(output_text=None), run_id="run-1", experiment_id="exp-1", agent_name="a")
    assert body["steps"] == [{"source": "agent", "step_id": 1, "message": ""}]


def test_trial_to_atif_ingest_includes_final_metrics_when_given() -> None:
    body = trial_to_atif_ingest(
        _trial(),
        run_id="run-1",
        experiment_id="exp-1",
        agent_name="a",
        final_metrics={"total_prompt_tokens": 10},
    )
    assert body["final_metrics"] == {"total_prompt_tokens": 10}


# --- score_to_evaluator_results: data_type coercions ------------------------


def test_score_row_naming_and_targeting() -> None:
    rows = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="score", value=0.5)]),
        session_id="run-1:trial-1",
        span_id="span-abc",
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "accuracy.score"
    assert rows[0]["session_id"] == "run-1:trial-1"
    assert rows[0]["span_id"] == "span-abc"


def test_one_row_per_output() -> None:
    rows = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="a", value=1.0), MetricOutput(name="b", value=2.0)]),
        session_id="s",
        span_id="span",
    )
    assert [row["name"] for row in rows] == ["accuracy.a", "accuracy.b"]


@pytest.mark.parametrize("value", [True, BooleanValue(True)])
def test_boolean_coercion_true(value: object) -> None:
    row = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="passed", value=value)]), session_id="s", span_id="sp"
    )[0]
    assert row["data_type"] == "BOOLEAN"
    assert row["value"] == 1.0
    assert "string_value" not in row


@pytest.mark.parametrize("value", [False, BooleanValue(False)])
def test_boolean_coercion_false(value: object) -> None:
    row = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="passed", value=value)]), session_id="s", span_id="sp"
    )[0]
    assert row["data_type"] == "BOOLEAN"
    assert row["value"] == 0.0


@pytest.mark.parametrize("value", [0.87, 3, ContinuousScore(0.87), DiscreteScore(3)])
def test_numeric_coercion(value: object) -> None:
    row = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="m", value=value)]), session_id="s", span_id="sp"
    )[0]
    assert row["data_type"] == "NUMERIC"
    assert isinstance(row["value"], float)
    assert "string_value" not in row


@pytest.mark.parametrize("value", ["PASS", Label("PASS")])
def test_text_coercion(value: object) -> None:
    row = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="verdict", value=value)]), session_id="s", span_id="sp"
    )[0]
    assert row["data_type"] == "TEXT"
    assert row["string_value"] == "PASS"
    assert "value" not in row


def test_comment_taken_from_first_diagnostic() -> None:
    score = _score(
        outputs=[MetricOutput(name="score", value=1.0)],
        diagnostics=[
            AgentEvalDiagnostic(severity=AgentEvalDiagnosticSeverity.WARNING, message="first"),
            AgentEvalDiagnostic(severity=AgentEvalDiagnosticSeverity.INFO, message="second"),
        ],
    )
    row = score_to_evaluator_results(score, session_id="s", span_id="sp")[0]
    assert row["comment"] == "first"


def test_comment_absent_without_diagnostics() -> None:
    row = score_to_evaluator_results(
        _score(outputs=[MetricOutput(name="score", value=1.0)]), session_id="s", span_id="sp"
    )[0]
    assert "comment" not in row
