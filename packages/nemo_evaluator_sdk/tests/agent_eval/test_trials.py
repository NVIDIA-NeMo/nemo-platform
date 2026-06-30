# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.trials import (
    AgentEvalTrial,
    AgentEvalTrialStatus,
    resolve_trial_status,
    standard_evidence_descriptors,
)


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
