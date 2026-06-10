# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable agent-eval metrics.

``AgentPhaseSuccessMetric`` reads the agent-phase outcome stamped on attempt
metadata. ``EvidencePresenceMetric`` is a genuine *metric-over-evidence*: it
scores by inspecting ``candidate.evidence`` (a filesystem evidence handle)
rather than a reward written into metadata — the value proposition of scoring
over evidence instead of trusting a verifier's stamped reward.
"""

from __future__ import annotations

from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class AgentPhaseSuccessMetric:
    """Score 1.0 when the agent phase exited successfully, else 0.0.

    The metric ``type`` is overridable via the ``metric_type`` class attribute so
    callers can namespace it; the output name stays ``agent_phase_success`` (which
    gating reads as a reward signal).
    """

    metric_type: str = "agent_phase_success"

    @property
    def type(self) -> str:
        return self.metric_type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("agent_phase_success")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        agent_ok = bool(input.candidate.metadata.get("agent_ok"))
        return MetricResult(outputs=[MetricOutput(name="agent_phase_success", value=1.0 if agent_ok else 0.0)])


class EvidencePresenceMetric:
    """Score 1.0 when a named filesystem evidence directory exists (and is non-empty).

    Reads ``candidate.evidence`` directly — the canonical metric-over-evidence
    pattern — so the score reflects what the agent actually produced on disk,
    not a reward stamped into metadata by a verifier.
    """

    def __init__(
        self,
        *,
        evidence_name: str = "final_state",
        output_name: str = "evidence_present",
        require_non_empty: bool = True,
    ) -> None:
        self._evidence_name = evidence_name
        self._output_name = output_name
        self._require_non_empty = require_non_empty

    @property
    def type(self) -> str:
        return "evidence_presence"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self._output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        score = 0.0
        evidence = input.candidate.evidence
        if evidence is not None and evidence.get(self._evidence_name) is not None:
            try:
                handle = await evidence.filesystem(self._evidence_name)
                if await handle.exists():
                    if self._require_non_empty:
                        score = 1.0 if await handle.iter_paths(recursive=True) else 0.0
                    else:
                        score = 1.0
            except (KeyError, ValueError):
                score = 0.0
        return MetricResult(outputs=[MetricOutput(name=self._output_name, value=score)])
