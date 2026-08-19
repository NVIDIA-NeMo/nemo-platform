# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.trials import (
    AgentEvalTrial,
    AgentEvalTrialStatus,
    TrialError,
    resolve_trial_status,
    standard_evidence_descriptors,
)
from pydantic import ValidationError


def test_trial_accepts_mapping_shaped_evidence_and_serializes_descriptors() -> None:
    # Evidence accepts a bare {name: descriptor} mapping (coerced to CandidateEvidence);
    # drive it through model_validate so the mapping shape is exercised end-to-end.
    trial = AgentEvalTrial.model_validate(
        {
            "id": "trial-1",
            "task_id": "task-1",
            "status": "completed",
            "output": {"output_text": "Answer"},
            "evidence": {
                "final_state": {"kind": "filesystem", "ref": "runs/local/final-state"},
                "trace": {"kind": "trace", "format": "atif", "ref": "runs/local/trace.atif.json"},
            },
        }
    )

    assert trial.evidence is not None
    assert trial.evidence.require("final_state", kind="filesystem").ref == "runs/local/final-state"
    assert trial.model_dump(mode="json")["evidence"] == {
        "descriptors": {
            "final_state": {
                "kind": "filesystem",
                "ref": "runs/local/final-state",
                "format": None,
                "data": None,
                "metadata": {},
            },
            "trace": {
                "kind": "trace",
                "ref": "runs/local/trace.atif.json",
                "format": "atif",
                "data": None,
                "metadata": {},
            },
        },
        "metadata": {},
    }


def test_completed_trial_requires_output() -> None:
    with pytest.raises(ValueError, match="completed trial requires output"):
        AgentEvalTrial(id="trial-1", task_id="task-1", status=AgentEvalTrialStatus.COMPLETED)


def test_resolve_trial_status_maps_ran_but_failed_to_partial() -> None:
    assert resolve_trial_status(True) == AgentEvalTrialStatus.COMPLETED
    # A ran-but-unsuccessful agent stays scorable (PARTIAL), not dropped (FAILED).
    assert resolve_trial_status(False) == AgentEvalTrialStatus.PARTIAL


def test_standard_evidence_descriptors_builds_documented_keys(tmp_path: Path) -> None:
    verifier_dir = tmp_path / "verifier"
    verifier_dir.mkdir()
    descriptors = standard_evidence_descriptors(
        logs_dir=tmp_path / "agent",
        final_state_dir=tmp_path / "workspace",
        trace_path=tmp_path / "atif-trace.json",
        initial_state_ref="s3://inputs",
        verifier_logs_dir=verifier_dir,
        primary_log="agent.log",
    )
    assert set(descriptors) == {"initial_state", "trace", "logs", "final_state", "verifier_logs"}
    assert descriptors["trace"].format == "atif"
    assert descriptors["logs"].metadata == {"primary_log": "agent.log"}

    # A missing verifier dir is omitted; trace is optional.
    minimal = standard_evidence_descriptors(logs_dir=tmp_path / "a", final_state_dir=tmp_path / "w")
    assert set(minimal) == {"logs", "final_state"}


def test_trial_error_rejects_an_empty_type() -> None:
    # An empty type would become an empty rollup key, which names nothing. The Harbor adapter
    # normalises before it gets here; this is the backstop for every other producer.
    for blank in ("", "   "):
        with pytest.raises(ValidationError, match="must not be empty"):
            TrialError(type=blank)


def test_trial_error_is_frozen_and_forbids_extras() -> None:
    error = TrialError(type="RuntimeError")

    with pytest.raises(ValidationError):
        error.type = "TimeoutError"
    with pytest.raises(ValidationError):
        TrialError(type="RuntimeError", stack="...")  # ty: ignore[unknown-argument]


def test_trial_error_round_trips_every_field_through_json() -> None:
    trial = AgentEvalTrial(
        id="t0",
        task_id="task-a",
        status=AgentEvalTrialStatus.PARTIAL,
        error=TrialError(
            type="RuntimeError",
            message="boom",
            traceback="Traceback (most recent call last):\n",
            occurred_at=datetime(2026, 8, 13, 17, 22, 32, 230852),
        ),
    )

    reloaded = AgentEvalTrial.model_validate(trial.model_dump(mode="json"))

    assert reloaded.error == trial.error
    assert AgentEvalTrial.model_validate(reloaded.model_dump(mode="json")).error == trial.error


def test_error_is_read_only_from_the_typed_field() -> None:
    # `error` is the single carrier. A bundle written before it existed recorded the type in
    # free-form metadata, and that is deliberately NOT interpreted: metadata stays opaque, so a
    # pre-TrialError bundle re-scores with no error rollup rather than a guessed one.
    trial = AgentEvalTrial.model_validate(
        {
            "id": "t0",
            "task_id": "task-a",
            "status": "partial",
            "metadata": {"exception_type": "TimeoutError", "reward": 0.0},
        }
    )

    assert trial.error is None
    assert trial.metadata["exception_type"] == "TimeoutError"  # kept verbatim, just not read


def test_a_trial_without_any_error_signal_loads_unchanged() -> None:
    trial = AgentEvalTrial.model_validate({"id": "t0", "task_id": "task-a", "status": "partial"})

    assert trial.error is None
    assert trial.metadata == {}
