# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_evaluator_sdk.agent_eval import (
    AgentEvalMetricSpec,
    AgentEvalTask,
    EvidenceLocator,
    ScoreDeduction,
)
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.values import CandidateEvidence, EvidenceDescriptor


def test_task_rejects_duplicate_metric_ids() -> None:
    with pytest.raises(ValueError, match="duplicate task metric ids"):
        AgentEvalTask(
            id="task-1",
            intent="answer the prompt",
            inputs={"prompt": "Question?"},
            metrics=[
                AgentEvalMetricSpec(id="metric", type="profbench_rubric"),
                AgentEvalMetricSpec(id="metric", type="other"),
            ],
        )


def test_score_deduction_requires_evidence() -> None:
    with pytest.raises(ValueError):
        ScoreDeduction(
            raw_points=1,
            normalized_impact=0.25,
            criterion_id="criterion-1",
            reason="missing evidence",
            evidence=[],
        )


def test_atif_evidence_requires_line_number() -> None:
    with pytest.raises(ValueError, match="ATIF evidence locators require a line number"):
        EvidenceLocator(kind="atif", uri="atif://attempt-trace")


def test_metric_input_preserves_candidate_evidence_out_of_metadata() -> None:
    evidence = CandidateEvidence(
        trace=EvidenceDescriptor(kind="atif", ref="atif://attempt-trace#L9", format="atif")
    )

    metric_input = build_metric_input(
        {"prompt": "Question?"},
        {"output_text": "Answer", "evidence": evidence, "custom": "metadata"},
        index=3,
    )

    assert metric_input.candidate.evidence == evidence
    assert metric_input.candidate.metadata == {"custom": "metadata"}
