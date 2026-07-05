# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Data contracts for the behavioral hardening loop."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


@dataclass
class AttackHit:
    """One garak hit (a detected exploit) parsed from a hitlog line."""

    probe: str
    prompt: str
    output: str
    detector: str
    index: int
    tool: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttackResult:
    """The Attack stage output for one round."""

    probes: list[str]
    hits: list[AttackHit]
    total_attempts: int
    seed: int

    @property
    def attack_success_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return len(self.hits) / self.total_attempts


@dataclass
class BehavioralFinding:
    """A hit routed as behaviorally relevant, with the matched reason tags."""

    finding_id: str
    attack_index: int
    record_index: int | None
    text: str
    record: dict[str, Any]
    guardrails_reasons: tuple[str, ...]


@dataclass
class GuardrailRemediation:
    """One guardrail-rail remediation for one finding.

    Phase 1 emits managed NeMo Guardrails input/output rails (see plan OQ1); the
    guardrail prompt is the rail's check content, and ``rail_type`` selects the
    ``input`` or ``output`` rail it lands on.
    """

    finding_id: str
    attack_prompt: str
    victim_response: str
    guardrail_prompt: str
    rail_type: str = "input"


@dataclass
class VerifyResult:
    """Result of replay or benign verification."""

    total: int
    passed: int
    failed: int
    errored: int
    detail: list[dict[str, Any]]

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total


@dataclass
class HardeningRound:
    index: int
    attack_success_rate: float
    benign_pass_rate: float
    remediation_count: int
    experiment_name: str


@dataclass
class HardeningState:
    rounds: list[HardeningRound] = field(default_factory=list)
    experiment_group_id: str = ""
    guardrail_config_name: str = ""


def _serialize(obj: Any) -> Any:
    """Recursively convert dataclasses (and Enum/Path) into JSON-able values.

    Matches ``improvement/models.py:_serialize`` so job results serialize the
    same way across the plugin. ``dataclasses.asdict`` alone would choke on
    ``Enum``/``Path`` fields added later; this handles them.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _serialize(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    return obj
