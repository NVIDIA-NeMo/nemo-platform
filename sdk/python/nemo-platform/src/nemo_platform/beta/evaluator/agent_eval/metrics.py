# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable agent-eval metrics and the typed view over trial measurements.

Two complementary pieces, both keyed off ``AgentEvalTrial``:

* Metrics (scorers) — ``AgentPhaseSuccessMetric`` reads the agent-phase outcome
  stamped on trial metadata; ``EvidencePresenceMetric`` is a genuine
  *metric-over-evidence* that scores by inspecting ``candidate.evidence`` (a
  filesystem evidence handle) rather than trusting a verifier's stamped reward.
* ``TrialMeasurements`` — the single documented place that names the loose
  metadata keys gating/reporting read, applying the fallbacks (``duration_ms`` →
  ``runtime_sec``, ``passed`` → ``reward``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.trials import EVIDENCE_FINAL_STATE
from nemo_platform.beta.evaluator.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# Token-measurement keys carried on trial metadata (and in result.json["metrics"]).
TOKEN_KEYS: tuple[str, ...] = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
)


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
        # Only an explicit boolean counts as success; a stray truthy string
        # (e.g. "false") must not mark a failed trial as passed.
        raw_agent_ok = input.candidate.metadata.get("agent_ok")
        agent_ok = raw_agent_ok if isinstance(raw_agent_ok, bool) else False
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
        evidence_name: str = EVIDENCE_FINAL_STATE,
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


class TrialMeasurements(BaseModel):
    """Numeric measurements projected from trial metadata.

    Reporting/gating consume it via :meth:`from_metadata`; producers keep writing
    the same keys onto ``AgentEvalTrial.metadata``.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cache_read_tokens: int | None = None
    runtime_sec: float | None = None
    reward: float | None = None
    passed: bool | None = None

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any] | None) -> TrialMeasurements:
        """Project loose trial metadata onto the typed contract.

        Applies the historical fallbacks so callers don't re-implement them:
        ``runtime_sec`` falls back to ``duration_ms / 1000``; ``reward`` falls
        back to ``1.0``/``0.0`` derived from ``passed`` when no explicit reward
        is recorded.
        """
        metadata = metadata or {}

        tokens = {key: _as_int(metadata.get(key)) for key in TOKEN_KEYS}
        passed = metadata.get("passed")
        passed = bool(passed) if isinstance(passed, bool) else None

        return cls(
            **tokens,
            runtime_sec=_runtime_sec(metadata),
            reward=_reward(metadata, passed),
            passed=passed,
        )


def _as_int(value: Any) -> int | None:
    # bool is an int subclass; never treat True/False as a token count.
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _runtime_sec(metadata: Mapping[str, Any]) -> float | None:
    runtime_sec = metadata.get("runtime_sec")
    if isinstance(runtime_sec, int | float) and not isinstance(runtime_sec, bool):
        return float(runtime_sec)
    duration_ms = metadata.get("duration_ms")
    if isinstance(duration_ms, int | float) and not isinstance(duration_ms, bool):
        return float(duration_ms) / 1000.0
    return None


def _reward(metadata: Mapping[str, Any], passed: bool | None) -> float | None:
    reward = metadata.get("reward")
    if reward is not None:
        try:
            return float(reward)
        except (TypeError, ValueError):
            return None
    if passed is not None:
        return 1.0 if passed else 0.0
    return None
