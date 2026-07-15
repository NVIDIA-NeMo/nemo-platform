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

import json
import logging
from collections.abc import Mapping
from typing import Any

from nemo_evaluator_sdk.agent_eval.trials import EVIDENCE_FINAL_STATE
from nemo_evaluator_sdk.metrics.protocol import (
    CandidateOutput,
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)
from nemo_evaluator_sdk.values.atif import Trajectory
from nemo_evaluator_sdk.values.evidence import EVIDENCE_TRACE
from pydantic import BaseModel, ConfigDict, ValidationError

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


class SkillUsedMetric:
    """Emit ``skill_present`` and ``skill_used`` so an eval can flag a failure to use an injected skill.

    * ``skill_present`` — ``True`` when a skill was injected into the trial. Reads the provenance a
      skill-aware runtime stamps onto candidate metadata under the ``"skill"`` key
      (``{"name", "hash", "mode", "adapter_id", "location", ...}``, see ``fabric.skills.SkillProvenance``);
      baseline trials carry none.
    * ``skill_used`` — best-effort ``True`` when the agent referenced the injected skill in its ATIF
      trajectory. It matches the skill's staged ``location`` (a specific, low-false-positive path
      signal — e.g. a read of ``.agents/skills/<name>/SKILL.md``) against tool-call names/arguments,
      step messages, reasoning, and observations. A bare skill-*name* match is intentionally NOT
      counted (the name commonly appears in the task prompt), so ``skill_present=True, skill_used=False``
      flags a *likely* failure to use the skill.

    Limitation: an absent trajectory reference cannot fully distinguish "not used" from "used without
    leaving a filesystem trace" — strongest for codex-style filesystem discovery, weaker for in-context
    skill loading. Authoritative usage detection via harness skill-activation events is a follow-up.
    With no skill present, both outputs are ``False``.
    """

    metric_type: str = "skill_used"
    OUTPUT_PRESENT: str = "skill_present"
    OUTPUT_USED: str = "skill_used"
    # Metadata key skill-aware runtimes stamp the provenance under (matches the fabric runtime).
    _METADATA_KEY: str = "skill"

    def __init__(self, *, trace_evidence: str = EVIDENCE_TRACE) -> None:
        self._trace_evidence = trace_evidence

    @property
    def type(self) -> str:
        return self.metric_type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [
            MetricOutputSpec.boolean(self.OUTPUT_PRESENT),
            MetricOutputSpec.boolean(self.OUTPUT_USED),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        provenance = input.candidate.metadata.get(self._METADATA_KEY)
        present = isinstance(provenance, Mapping) and bool(provenance)
        used = await self._skill_used(input.candidate, provenance) if present else False
        return MetricResult(
            outputs=[
                MetricOutput(name=self.OUTPUT_PRESENT, value=present),
                MetricOutput(name=self.OUTPUT_USED, value=used),
            ]
        )

    async def _skill_used(self, candidate: CandidateOutput, provenance: Mapping[str, Any]) -> bool:
        location = provenance.get("location")
        if not isinstance(location, str) or not location:
            return False
        evidence = candidate.evidence
        if evidence is None or evidence.get(self._trace_evidence) is None:
            return False
        try:
            trajectory = await (await evidence.trace(self._trace_evidence)).trace()
        except (KeyError, ValueError, ValidationError, OSError) as exc:
            # Best-effort: a missing/malformed/invalid trajectory must score skill_used=False, not raise.
            # ValidationError covers Trajectory.model_validate; OSError covers the underlying file read.
            logger.warning(
                "SkillUsedMetric scored skill_used=False: could not read trace %r: %s", self._trace_evidence, exc
            )
            return False
        return _trajectory_references(trajectory, location)


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


def _trajectory_references(trajectory: Trajectory, needle: str) -> bool:
    """Whether ``needle`` appears anywhere an agent action could reference the skill.

    Scans each step's message, reasoning, tool calls (name + arguments), and observation results.
    """
    for step in trajectory.steps:
        if needle in step.message or (step.reasoning_content is not None and needle in step.reasoning_content):
            return True
        for call in step.tool_calls or []:
            if needle in call.function_name:
                return True
            if call.arguments is not None and needle in json.dumps(call.arguments, default=str):
                return True
        if step.observation is not None:
            for result in step.observation.results:
                if result.content is not None and needle in json.dumps(result.content, default=str):
                    return True
    return False


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
