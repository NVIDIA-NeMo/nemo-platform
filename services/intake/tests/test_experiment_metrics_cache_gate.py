# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The list read path only trusts denormalized metrics on a version+decode match, else falls back."""

from __future__ import annotations

from nmp.intake.api.v2.experiments.endpoints import _cached_rollup
from nmp.intake.spans.experiment_rollup_repository import METRICS_VERSION, ExperimentRollup, rollup_to_metrics


def _metrics() -> dict:
    rollup = ExperimentRollup(experiment_id="exp", run_count=3)
    return rollup_to_metrics(rollup, refreshed_at="2026-06-23T00:00:00+00:00")


def test_decodes_current_version() -> None:
    rollup = _cached_rollup("exp", _metrics())
    assert rollup is not None
    assert rollup.run_count == 3


def test_none_when_absent() -> None:
    assert _cached_rollup("exp", None) is None
    assert _cached_rollup("exp", {}) is None


def test_none_on_version_mismatch() -> None:
    stale = _metrics()
    stale["version"] = METRICS_VERSION + 1
    assert _cached_rollup("exp", stale) is None


def test_none_on_malformed_blob() -> None:
    # Right version, but a shape that blows up decode -> treated as cache-miss, not an exception.
    assert _cached_rollup("exp", {"version": METRICS_VERSION, "evaluators": "not-a-dict"}) is None
