# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed view over the measurement keys carried on ``AgentEvalAttempt.metadata``.

Gating and reporting read these typed fields instead of reaching into the
attempt metadata dict by magic string. The keys are still *stored* on
``metadata`` (so the loose-dict contract continues to work during migration);
this module is the single, documented place that names them and applies the
fallbacks (``duration_ms`` → ``runtime_sec``, ``passed`` → ``reward``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Token-measurement keys carried on attempt metadata (and in result.json["metrics"]).
TOKEN_KEYS: tuple[str, ...] = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
)


class AttemptMeasurements(BaseModel):
    """Numeric measurements + provenance projected from attempt metadata.

    This is the public, typed attempt-measurement contract. Reporting/gating
    consume it via :meth:`from_metadata`; producers may keep writing the same
    keys onto ``AgentEvalAttempt.metadata`` and round-trip via :meth:`to_metadata`.
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
    provenance: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any] | None) -> AttemptMeasurements:
        """Project loose attempt metadata onto the typed contract.

        Applies the historical fallbacks so callers don't re-implement them:
        ``runtime_sec`` falls back to ``duration_ms / 1000``; ``reward`` falls
        back to ``1.0``/``0.0`` derived from ``passed`` when no explicit reward
        is recorded.
        """
        metadata = metadata or {}

        tokens = {key: _as_int(metadata.get(key)) for key in TOKEN_KEYS}
        runtime_sec = _runtime_sec(metadata)
        passed = metadata.get("passed")
        passed = bool(passed) if isinstance(passed, bool) else None
        reward = _reward(metadata, passed)
        provenance = metadata.get("provenance")
        provenance = dict(provenance) if isinstance(provenance, Mapping) else {}

        return cls(
            **tokens,
            runtime_sec=runtime_sec,
            reward=reward,
            passed=passed,
            provenance=provenance,
        )

    def to_metadata(self) -> dict[str, Any]:
        """Project back onto the loose metadata keys (only set values)."""
        payload: dict[str, Any] = {}
        for key in TOKEN_KEYS:
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.runtime_sec is not None:
            payload["runtime_sec"] = self.runtime_sec
        if self.reward is not None:
            payload["reward"] = self.reward
        if self.passed is not None:
            payload["passed"] = self.passed
        if self.provenance:
            payload["provenance"] = dict(self.provenance)
        return payload


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
