# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvalAttempt, AgentEvalTask, AgentOutput
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


def test_attempt_accepts_mapping_shaped_evidence_and_serializes_descriptors() -> None:
    attempt = AgentEvalAttempt(
        id="attempt-1",
        task_id="task-1",
        output=AgentOutput(text="Answer"),
        evidence={
            "final_state": EvidenceDescriptor(kind="filesystem", ref="runs/local/final-state"),
            "trace": EvidenceDescriptor(kind="trace", format="atif", ref="runs/local/trace.atif.json"),
        },
    )

    assert attempt.evidence is not None
    assert attempt.evidence.require("final_state", kind="filesystem").ref == "runs/local/final-state"
    assert attempt.model_dump(mode="json")["evidence"] == {
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


@pytest.mark.asyncio
async def test_candidate_evidence_filesystem_access_is_lazy_and_cached(tmp_path: Path) -> None:
    final_state = tmp_path / "final"
    final_state.mkdir()
    (final_state / "answer.txt").write_text("done", encoding="utf-8")
    (final_state / "nested").mkdir()
    (final_state / "nested" / "notes.txt").write_text("notes", encoding="utf-8")

    evidence = CandidateEvidence(
        descriptors={
            "remote_state": EvidenceDescriptor(kind="filesystem", ref="https://example.test/archive.tgz"),
            "final_state": EvidenceDescriptor(kind="filesystem", ref=str(final_state)),
        }
    )

    assert evidence.require("remote_state", kind="filesystem").ref == "https://example.test/archive.tgz"

    handle = await evidence.filesystem("final_state")
    cached = await evidence.filesystem("final_state")

    assert handle is cached
    assert await handle.exists("answer.txt") is True
    assert await handle.read_text("answer.txt") == "done"
    assert await handle.iter_paths(recursive=True) == ["answer.txt", "nested", "nested/notes.txt"]
    with pytest.raises(ValueError, match="outside evidence root"):
        handle.path("../outside")
    with pytest.raises(ValueError, match="only supports local filesystem"):
        await evidence.filesystem("remote_state")
