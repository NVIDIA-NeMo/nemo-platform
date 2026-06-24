# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nemo_deployments_plugin.reconciler.drift_recovery import DriftRecoveryCache, DriftRecoveryLimits, RecoveryAction

LIMITS = DriftRecoveryLimits(max_attempts=3, initial_delay_seconds=1, max_delay_seconds=10)


def test_should_recover_proceed_when_untracked() -> None:
    cache = DriftRecoveryCache()
    assert cache.should_recover("ws/dep", LIMITS) == RecoveryAction.PROCEED


def test_should_recover_exhausted_at_max_attempts() -> None:
    cache = DriftRecoveryCache()
    cache.add_attempt("ws/dep")
    cache.add_attempt("ws/dep")
    cache.add_attempt("ws/dep")
    assert cache.should_recover("ws/dep", LIMITS) == RecoveryAction.EXHAUSTED


def test_should_recover_backoff() -> None:
    cache = DriftRecoveryCache()
    cache.add_attempt("ws/dep")
    assert (
        cache.should_recover(
            "ws/dep", DriftRecoveryLimits(max_attempts=5, initial_delay_seconds=60, max_delay_seconds=300)
        )
        == RecoveryAction.BACKOFF
    )


def test_first_backoff_uses_base_delay_not_doubled() -> None:
    cache = DriftRecoveryCache()
    cache.add_attempt("ws/dep")
    limits = DriftRecoveryLimits(max_attempts=5, initial_delay_seconds=10, max_delay_seconds=300)
    state = cache._states["ws/dep"]
    assert state.attempts == 1
    assert cache.should_recover("ws/dep", limits) == RecoveryAction.BACKOFF
    state.last_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=9)
    assert cache.should_recover("ws/dep", limits) == RecoveryAction.BACKOFF
    state.last_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=11)
    assert cache.should_recover("ws/dep", limits) == RecoveryAction.PROCEED


def test_should_recover_proceed_after_backoff() -> None:
    cache = DriftRecoveryCache()
    cache.add_attempt("ws/dep")
    cache._states["ws/dep"].last_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    assert cache.should_recover("ws/dep", LIMITS) == RecoveryAction.PROCEED


def test_remove_clears_state() -> None:
    cache = DriftRecoveryCache()
    cache.add_attempt("ws/dep")
    cache.remove("ws/dep")
    assert cache.get_attempts("ws/dep") == 0
