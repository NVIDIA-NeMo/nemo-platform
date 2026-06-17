# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus


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
