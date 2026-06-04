# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvalTask
from nemo_evaluator_sdk.agent_eval.types import SemanticView, ViewSignal
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import CandidateEvidence, EvidenceDescriptor


class _Metric:
    @property
    def type(self) -> str:
        return "example_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        raise NotImplementedError


def test_task_serializes_metric_instances_as_descriptors() -> None:
    task = AgentEvalTask(
        id="task-1",
        intent="answer the prompt",
        inputs={"prompt": "Question?"},
        metrics=[_Metric()],
    )

    assert task.model_dump(mode="json")["metrics"] == [
        {
            "type": "example_metric",
            "outputs": [{"name": "score", "description": None, "value_schema": "ContinuousScore"}],
        }
    ]


def test_task_rejects_duplicate_metric_types() -> None:
    with pytest.raises(ValueError, match="duplicate task metric types"):
        AgentEvalTask(
            id="task-1",
            intent="answer the prompt",
            inputs={"prompt": "Question?"},
            metrics=[_Metric(), _Metric()],
        )


def test_task_validates_view_signals_against_metric_outputs() -> None:
    with pytest.raises(ValueError, match="unknown output"):
        AgentEvalTask(
            id="task-1",
            intent="answer the prompt",
            inputs={"prompt": "Question?"},
            metrics=[_Metric()],
            views={
                "outcome_correctness": SemanticView(
                    reducer="single",
                    signals=[ViewSignal(metric="example_metric", output="missing")],
                )
            },
        )


def test_metric_input_preserves_candidate_evidence_out_of_metadata() -> None:
    evidence = CandidateEvidence(
        descriptors={"trace": EvidenceDescriptor(kind="atif", ref="atif://attempt-trace#L9", format="atif")}
    )

    metric_input = build_metric_input(
        {"prompt": "Question?"},
        {"output_text": "Answer", "evidence": evidence, "custom": "metadata"},
        index=3,
    )

    assert metric_input.candidate.evidence == evidence
    assert metric_input.candidate.evidence is not None
    assert metric_input.candidate.evidence.require("trace", kind="atif") == evidence.descriptors["trace"]
    assert metric_input.candidate.metadata == {"custom": "metadata"}
