# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for evaluator_agent_eval.schemas."""

import pytest
from evaluator_agent_eval.schemas import (
    AgentAttemptInput,
    AgentAttemptMetadata,
    AgentAttemptOutput,
    CapturedAgentAttempt,
    EvaluatorScoringRow,
    TrajectorySummary,
)


def _attempt(**overrides: object) -> CapturedAgentAttempt:
    data = {
        "task_id": "run-simple-exact-match",
        "input": {"instruction_text": "Do the task."},
        "output": {"final_text": "done", "final_answer_extracted": True},
        "metadata": {"agent_runtime": "codex", "agent_model": "gpt-5.4"},
    }
    data.update(overrides)
    return CapturedAgentAttempt.model_validate(data)


def _scoring_row(**overrides: object) -> EvaluatorScoringRow:
    data = {
        "task_id": "run-simple-exact-match",
        "agent_runtime": "codex",
        "agent_model": "gpt-5.4",
        "surface_constraint": "standalone_sdk",
        "allowed_surfaces": ["standalone_sdk"],
    }
    data.update(overrides)
    return EvaluatorScoringRow.model_validate(data)


def test_attempt_schema_is_generic():
    attempt = _attempt()

    assert attempt.input == AgentAttemptInput(instruction_text="Do the task.")
    assert attempt.output == AgentAttemptOutput(final_text="done", final_answer_extracted=True)
    assert attempt.metadata == AgentAttemptMetadata(agent_runtime="codex", agent_model="gpt-5.4")


def test_attempt_schema_rejects_eval_policy_fields():
    with pytest.raises(ValueError, match="surface_constraint"):
        _attempt(surface_constraint="standalone_sdk")


def test_scoring_row_rejects_missing_allowed_surfaces():
    with pytest.raises(ValueError, match="allowed_surfaces"):
        _scoring_row(allowed_surfaces=[])


def test_schema_rejects_judge_model_on_candidate_attempt():
    with pytest.raises(ValueError, match="judge_model"):
        _attempt(judge_model="judge-model")


def test_schema_keeps_candidate_model():
    row = _attempt(metadata={"agent_runtime": "codex", "agent_model": "candidate-model"})

    assert row.metadata.agent_model == "candidate-model"


def test_trajectory_summary_rejects_negative_counts():
    with pytest.raises(ValueError, match="non-negative"):
        TrajectorySummary(tool_call_count=-1)
