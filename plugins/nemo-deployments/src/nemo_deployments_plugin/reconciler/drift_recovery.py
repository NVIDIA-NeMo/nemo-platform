# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Drift recovery backoff tracking for lost deployments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto


class RecoveryAction(Enum):
    """Result of checking whether drift recovery should proceed."""

    PROCEED = auto()
    BACKOFF = auto()
    EXHAUSTED = auto()


@dataclass(frozen=True)
class DriftRecoveryLimits:
    max_attempts: int
    initial_delay_seconds: int
    max_delay_seconds: int


@dataclass
class DriftRecoveryState:
    attempts: int = 0
    last_attempt_at: datetime | None = None


class DriftRecoveryCache:
    """Tracks drift recovery attempts with exponential backoff."""

    def __init__(self) -> None:
        self._states: dict[str, DriftRecoveryState] = {}

    def add(self, deployment_id: str) -> None:
        if deployment_id not in self._states:
            self._states[deployment_id] = DriftRecoveryState()

    def remove(self, deployment_id: str) -> None:
        self._states.pop(deployment_id, None)

    def should_recover(self, deployment_id: str, limits: DriftRecoveryLimits) -> RecoveryAction:
        state = self._states.get(deployment_id)
        if state is None:
            return RecoveryAction.PROCEED
        if state.attempts >= limits.max_attempts:
            return RecoveryAction.EXHAUSTED
        if state.last_attempt_at:
            backoff_seconds = min(
                limits.initial_delay_seconds * (2 ** max(state.attempts - 1, 0)),
                limits.max_delay_seconds,
            )
            elapsed = (datetime.now(timezone.utc) - state.last_attempt_at).total_seconds()
            if elapsed < backoff_seconds:
                return RecoveryAction.BACKOFF
        return RecoveryAction.PROCEED

    def add_attempt(self, deployment_id: str) -> int:
        self.add(deployment_id)
        state = self._states[deployment_id]
        state.attempts += 1
        state.last_attempt_at = datetime.now(timezone.utc)
        return state.attempts

    def get_attempts(self, deployment_id: str) -> int:
        state = self._states.get(deployment_id)
        return state.attempts if state else 0
