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

import logging

from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult

logger = logging.getLogger(__name__)


class AgentPhaseSuccessMetric:
    """Emit ``True`` when the agent phase exited successfully, else ``False``.

    The metric ``type`` is overridable via the ``metric_type`` class attribute so
    callers can namespace it; the output name stays ``agent_phase_success`` (which
    gating reads as a reward signal — ``True``/``False`` coerces to ``1.0``/``0.0``).
    """

    metric_type: str = "agent_phase_success"

    @property
    def type(self) -> str:
        return self.metric_type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.boolean("agent_phase_success")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        agent_ok = bool(input.candidate.metadata.get("agent_ok"))
        return MetricResult(outputs=[MetricOutput(name="agent_phase_success", value=agent_ok)])


class EvidencePresenceMetric:
    """Emit ``True`` when a named filesystem evidence directory exists (and is non-empty).

    Reads ``candidate.evidence`` directly — the canonical metric-over-evidence
    pattern — so the result reflects what the agent actually produced on disk,
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
        return [MetricOutputSpec.boolean(self._output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        present = False
        evidence = input.candidate.evidence
        if evidence is not None and evidence.get(self._evidence_name) is not None:
            try:
                handle = await evidence.filesystem(self._evidence_name)
                if await handle.exists():
                    present = bool(await handle.iter_paths(recursive=True)) if self._require_non_empty else True
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "EvidencePresenceMetric scored False: could not resolve evidence %r for output %r: %s",
                    self._evidence_name,
                    self._output_name,
                    exc,
                )
        return MetricResult(outputs=[MetricOutput(name=self._output_name, value=present)])
