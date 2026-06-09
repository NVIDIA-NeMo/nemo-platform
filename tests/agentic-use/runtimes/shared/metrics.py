# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Default metrics for agentic-use agent-eval runs."""

from __future__ import annotations

from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class AgentPhaseSuccessMetric:
    """Score 1.0 when the agent phase exited successfully, else 0.0."""

    @property
    def type(self) -> str:
        return "agentic_use_agent_phase"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("agent_phase_success")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        agent_ok = bool(input.candidate.metadata.get("agent_ok"))
        return MetricResult(
            outputs=[MetricOutput(name="agent_phase_success", value=1.0 if agent_ok else 0.0)],
        )


class VerifierRewardMetric:
    """Compatibility metric mirroring the legacy pytest verifier reward.

    Reads the verifier outcome that ``nat_runner`` records in ``result.json``
    (projected onto attempt metadata as ``reward``/``passed``) so existing
    ``tests/test_outputs.py`` verifiers can score through the Evaluator SDK
    while task-specific metrics are authored.
    """

    @property
    def type(self) -> str:
        return "agentic_use_verifier_reward"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("verifier_reward")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        metadata = input.candidate.metadata
        reward = metadata.get("reward")
        if reward is None:
            reward = 1.0 if metadata.get("passed") else 0.0
        return MetricResult(
            outputs=[MetricOutput(name="verifier_reward", value=float(reward))],
        )
