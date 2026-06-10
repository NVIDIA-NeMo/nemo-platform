# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for promoted attempt helpers and reusable metrics."""

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.attempts import resolve_attempt_status, standard_evidence_descriptors
from nemo_evaluator_sdk.agent_eval.common_metrics import AgentPhaseSuccessMetric, EvidencePresenceMetric
from nemo_evaluator_sdk.metrics.protocol import CandidateOutput, DatasetRow, MetricInput
from nemo_evaluator_sdk.values.evidence import CandidateEvidence


def test_resolve_attempt_status_keeps_failed_agents_scorable() -> None:
    assert resolve_attempt_status(True) == "completed"
    assert resolve_attempt_status(False) == "partial"


def test_standard_evidence_descriptors_builds_doc_keys(tmp_path: Path) -> None:
    logs = tmp_path / "agent"
    workspace = tmp_path / "workspace"
    verifier = tmp_path / "verifier"
    logs.mkdir()
    workspace.mkdir()
    verifier.mkdir()  # exists -> verifier_logs included

    descriptors = standard_evidence_descriptors(
        logs_dir=logs,
        final_state_dir=workspace,
        trace_path=tmp_path / "atif_trajectory.json",
        initial_state_ref=str(tmp_path / "seed"),
        verifier_logs_dir=verifier,
        primary_log="nat_agent.log",
    )
    assert set(descriptors) == {"initial_state", "trace", "logs", "final_state", "verifier_logs"}
    assert descriptors["trace"].format == "atif"
    assert descriptors["logs"].metadata["primary_log"] == "nat_agent.log"

    # verifier_logs omitted when the dir is absent.
    no_verifier = standard_evidence_descriptors(
        logs_dir=logs, final_state_dir=workspace, verifier_logs_dir=tmp_path / "missing"
    )
    assert "verifier_logs" not in no_verifier


@pytest.mark.asyncio
async def test_agent_phase_success_metric_reads_metadata_and_namespaces_type() -> None:
    metric = AgentPhaseSuccessMetric()
    assert metric.type == "agent_phase_success"
    ok = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(metadata={"agent_ok": True}))
    )
    assert ok.outputs[0].value == 1.0

    class Namespaced(AgentPhaseSuccessMetric):
        metric_type = "agentic_use_agent_phase"

    assert Namespaced().type == "agentic_use_agent_phase"


@pytest.mark.asyncio
async def test_evidence_presence_metric_scores_over_evidence(tmp_path: Path) -> None:
    final_state = tmp_path / "workspace"
    final_state.mkdir()
    (final_state / "result.txt").write_text("done", encoding="utf-8")
    evidence = CandidateEvidence(
        descriptors=standard_evidence_descriptors(logs_dir=tmp_path / "agent", final_state_dir=final_state)
    )

    metric = EvidencePresenceMetric()
    present = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(evidence=evidence))
    )
    assert present.outputs[0].value == 1.0

    # Empty workspace -> non-empty requirement fails; no evidence -> 0.
    (final_state / "result.txt").unlink()
    empty = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(evidence=evidence))
    )
    assert empty.outputs[0].value == 0.0
    missing = await metric.compute_scores(MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput()))
    assert missing.outputs[0].value == 0.0
