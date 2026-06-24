# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the reusable agent-eval metrics and the TrialMeasurements contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.metrics import (
    AgentPhaseSuccessMetric,
    EvidencePresenceMetric,
    TrialMeasurements,
)
from nemo_evaluator_sdk.agent_eval.trials import standard_evidence_descriptors
from nemo_evaluator_sdk.metrics.protocol import CandidateOutput, DatasetRow, MetricInput
from nemo_evaluator_sdk.values.evidence import CandidateEvidence


@pytest.mark.asyncio
async def test_agent_phase_success_metric_reads_metadata_and_namespaces_type() -> None:
    metric = AgentPhaseSuccessMetric()
    assert metric.type == "agent_phase_success"
    ok = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(metadata={"agent_ok": True}))
    )
    assert ok.outputs[0].value is True

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
    assert present.outputs[0].value is True

    # Empty workspace -> non-empty requirement fails; no evidence -> False.
    (final_state / "result.txt").unlink()
    empty = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(evidence=evidence))
    )
    assert empty.outputs[0].value is False
    missing = await metric.compute_scores(MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput()))
    assert missing.outputs[0].value is False


def test_from_metadata_reads_tokens_runtime_reward() -> None:
    measurements = TrialMeasurements.from_metadata(
        {
            "total_tokens": 120,
            "prompt_tokens": 80,
            "completion_tokens": 40,
            "runtime_sec": 4.5,
            "reward": 1,
            "passed": True,
        }
    )
    assert measurements.total_tokens == 120
    assert measurements.runtime_sec == 4.5
    assert measurements.reward == 1.0
    assert measurements.passed is True


def test_from_metadata_applies_fallbacks_and_ignores_bad_types() -> None:
    # duration_ms -> runtime_sec, passed -> reward, bool is not a token count.
    measurements = TrialMeasurements.from_metadata({"duration_ms": 2500, "passed": False, "total_tokens": True})
    assert measurements.runtime_sec == 2.5
    assert measurements.reward == 0.0
    assert measurements.total_tokens is None

    empty = TrialMeasurements.from_metadata(None)
    assert empty.reward is None and empty.runtime_sec is None
