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
import math
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from nemo_evaluator_sdk.agent_eval.trials import EVIDENCE_FINAL_STATE
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.metrics.protocol import (
    CandidateOutput,
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)
from nemo_evaluator_sdk.values.atif import Trajectory
from nemo_evaluator_sdk.values.evidence import EVIDENCE_TRACE
from nemo_evaluator_sdk.values.metrics import MetricBase
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# Token-measurement keys carried on trial metadata (and in result.json["metrics"]).
TOKEN_KEYS: tuple[str, ...] = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
)


class AgentPhaseSuccessMetric(MetricBase):
    """Emit ``True`` when the agent phase exited successfully, else ``False``.

    The output name stays ``agent_phase_success`` (which gating reads as a reward
    signal — ``True``/``False`` coerces to ``1.0``/``0.0``).

    A built-in metric type, so it bundles inline and needs no cloudpickle opt-in to be
    stored on a task. ``type`` is therefore a fixed discriminator and no longer
    overridable per caller.
    """

    type: Literal[MetricType.AGENT_PHASE_SUCCESS] = MetricType.AGENT_PHASE_SUCCESS

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.boolean("agent_phase_success")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        # Only an explicit boolean counts as success; a stray truthy string
        # (e.g. "false") must not mark a failed trial as passed.
        raw_agent_ok = input.candidate.metadata.get("agent_ok")
        agent_ok = raw_agent_ok if isinstance(raw_agent_ok, bool) else False
        return MetricResult(outputs=[MetricOutput(name="agent_phase_success", value=agent_ok)])


class EvidencePresenceMetric(MetricBase):
    """Emit ``True`` when a named filesystem evidence directory exists (and is non-empty).

    Reads ``candidate.evidence`` directly — the canonical metric-over-evidence
    pattern — so the result reflects what the agent actually produced on disk,
    not a reward stamped into metadata by a verifier.
    """

    type: Literal[MetricType.EVIDENCE_PRESENCE] = MetricType.EVIDENCE_PRESENCE
    evidence_name: str = Field(default=EVIDENCE_FINAL_STATE, description="Evidence directory to look for.")
    output_name: str = Field(default="evidence_present", description="Name of the emitted boolean score.")
    require_non_empty: bool = Field(
        default=True, description="Require the evidence directory to be non-empty, not merely present."
    )

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.boolean(self.output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        present = False
        evidence = input.candidate.evidence
        if evidence is not None and evidence.get(self.evidence_name) is not None:
            try:
                handle = await evidence.filesystem(self.evidence_name)
                if await handle.exists():
                    present = bool(await handle.iter_paths(recursive=True)) if self.require_non_empty else True
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "EvidencePresenceMetric scored False: could not resolve evidence %r for output %r: %s",
                    self.evidence_name,
                    self.output_name,
                    exc,
                )
        return MetricResult(outputs=[MetricOutput(name=self.output_name, value=present)])


class SkillUsedMetric(MetricBase):
    """Emit ``skill_present`` and ``skill_used`` so an eval can flag a failure to use an injected skill.

    * ``skill_present`` — ``True`` when one or more skills were injected into the trial. Reads
      the ``"skills"`` metadata key a skill-aware runtime stamps — a list of provenance dicts
      (``{"name", "hash", "mode", "adapter_id", "location", ...}``, see ``fabric.skills.SkillProvenance``).
      Baseline trials carry an empty list.
    * ``skill_used`` — best-effort ``True`` when the agent referenced *any* injected skill in its ATIF
      trajectory. It matches each skill's staged ``location`` (a specific, low-false-positive path
      signal — e.g. a read of ``.agents/skills/<name>/SKILL.md``) against tool-call names/arguments,
      step messages, reasoning, and observations. A bare skill-*name* match is intentionally NOT
      counted (the name commonly appears in the task prompt), so ``skill_present=True, skill_used=False``
      flags a *likely* failure to use the skill.

    Limitation: an absent trajectory reference cannot fully distinguish "not used" from "used without
    leaving a filesystem trace" — strongest for codex-style filesystem discovery, weaker for in-context
    skill loading. Authoritative usage detection via harness skill-activation events is a follow-up.
    With no skill present, both outputs are ``False``.
    """

    type: Literal[MetricType.SKILL_USED] = MetricType.SKILL_USED
    trace_evidence: str = Field(default=EVIDENCE_TRACE, description="Trace evidence to scan for skill usage.")

    OUTPUT_PRESENT: ClassVar[str] = "skill_present"
    OUTPUT_USED: ClassVar[str] = "skill_used"
    # Metadata key skill-aware runtimes stamp the provenance list under (matches the fabric runtime).
    _SKILLS_KEY: ClassVar[str] = "skills"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [
            MetricOutputSpec.boolean(self.OUTPUT_PRESENT),
            MetricOutputSpec.boolean(self.OUTPUT_USED),
        ]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        provenances = self._extract_provenances(input.candidate.metadata)
        present = bool(provenances)
        used = await self._any_skill_used(input.candidate, provenances) if present else False
        return MetricResult(
            outputs=[
                MetricOutput(name=self.OUTPUT_PRESENT, value=present),
                MetricOutput(name=self.OUTPUT_USED, value=used),
            ]
        )

    def _extract_provenances(self, metadata: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        skills = metadata.get(self._SKILLS_KEY)
        if isinstance(skills, list):
            return [p for p in skills if isinstance(p, Mapping) and p]
        return []

    async def _any_skill_used(self, candidate: CandidateOutput, provenances: list[Mapping[str, Any]]) -> bool:
        locations = [loc for p in provenances if isinstance(loc := p.get("location"), str) and loc]
        if not locations:
            return False
        evidence = candidate.evidence
        if evidence is None or evidence.get(self.trace_evidence) is None:
            return False
        try:
            handle = await evidence.trace(self.trace_evidence)
            if handle.format == "otlp":
                resource_spans = await handle.resource_spans()
                return any(_otlp_references(resource_spans, loc) for loc in locations)
            trajectory = await handle.trace()
        except (KeyError, ValueError, ValidationError, OSError) as exc:
            # Best-effort: a missing/malformed/invalid trajectory must score skill_used=False, not raise.
            # ValidationError covers Trajectory.model_validate; OSError covers the underlying file read.
            logger.warning(
                "SkillUsedMetric scored skill_used=False: could not read trace %r: %s", self.trace_evidence, exc
            )
            return False
        return any(_trajectory_references(trajectory, loc) for loc in locations)


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
    cost_usd: float | None = Field(default=None, allow_inf_nan=False)
    reward: float | None = None
    passed: bool | None = None

    @field_validator("cost_usd", mode="before")
    @classmethod
    def _reject_boolean_cost(cls, value: Any) -> Any:
        """Refuse a ``bool`` cost, which coercion would otherwise hide.

        ``bool`` is an ``int`` subclass, so ``True`` would validate as a cost of 1.0. Every other
        unusable value is already refused: ``allow_inf_nan=False`` covers NaN and the infinities
        however they were spelled, and float coercion covers an int too large to represent.
        """
        if isinstance(value, bool):
            raise ValueError("cost_usd must be a number, not a bool")
        return value

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
            cost_usd=_as_float(metadata.get("cost_usd")),
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


def _otlp_references(resource_spans: list[dict[str, Any]], needle: str) -> bool:
    """Check whether an OTLP string payload references ``needle``.

    Args:
        resource_spans: OTLP resource-span export units.
        needle: Staged skill location to find.

    Returns:
        Whether any span or span-event string attribute contains ``needle``.
    """
    return any(needle in blob for blob in _otlp_string_blobs(resource_spans))


def _otlp_string_blobs(resource_spans: list[dict[str, Any]]) -> list[str]:
    """Collect searchable string attributes from OTLP spans and events.

    Args:
        resource_spans: OTLP resource-span export units.

    Returns:
        String values found beneath span and event attributes.
    """
    blobs: list[str] = []
    for resource_span in resource_spans:
        for scope_span in _otlp_dict_items(resource_span.get("scopeSpans")):
            for span in _otlp_dict_items(scope_span.get("spans")):
                blobs.extend(_otlp_attr_strings(span.get("attributes")))
                for event in _otlp_dict_items(span.get("events")):
                    blobs.extend(_otlp_attr_strings(event.get("attributes")))
    return blobs


def _otlp_dict_items(value: Any) -> list[dict[str, Any]]:
    """Return only dictionary elements from an OTLP repeated field.

    Args:
        value: Candidate decoded repeated field.

    Returns:
        Dictionary elements, or an empty list for malformed containers.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _otlp_attr_strings(attributes: Any) -> list[str]:
    """Collect string leaves from decoded OTLP attributes.

    Args:
        attributes: Candidate OTLP key-value attribute list.

    Returns:
        String leaves contained in each attribute value.
    """
    blobs: list[str] = []
    for item in _otlp_dict_items(attributes):
        blobs.extend(_otlp_any_strings(item.get("value")))
    return blobs


def _otlp_any_strings(value: Any) -> list[str]:
    """Collect string leaves from one decoded OTLP ``AnyValue``.

    Args:
        value: Candidate OTLP ``AnyValue`` object.

    Returns:
        Recursively nested string values.
    """
    if isinstance(value, str):
        return [value]
    if not isinstance(value, dict):
        return []
    if (text := value.get("stringValue")) is not None:
        return [str(text)]
    if isinstance(array := value.get("arrayValue"), dict):
        blobs: list[str] = []
        values = array.get("values")
        if isinstance(values, list):
            for item in values:
                blobs.extend(_otlp_any_strings(item))
        return blobs
    if isinstance(kvlist := value.get("kvlistValue"), dict):
        blobs = []
        for item in _otlp_dict_items(kvlist.get("values")):
            blobs.extend(_otlp_any_strings(item.get("value")))
        return blobs
    return []


def _as_int(value: Any) -> int | None:
    # bool is an int subclass; never treat True/False as a token count.
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _as_float(value: Any) -> float | None:
    # bool is an int subclass; never treat True/False as a measurement. NaN, the infinities, and
    # integers too large to represent are rejected too: none can be serialised onto the wire, so
    # recording one would fail the publish of an otherwise good trial.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


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
