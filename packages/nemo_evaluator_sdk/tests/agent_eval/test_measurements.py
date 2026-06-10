# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the typed AttemptMeasurements contract."""

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval.measurements import AttemptMeasurements


def test_from_metadata_reads_tokens_runtime_reward_and_provenance() -> None:
    measurements = AttemptMeasurements.from_metadata(
        {
            "total_tokens": 120,
            "prompt_tokens": 80,
            "completion_tokens": 40,
            "runtime_sec": 4.5,
            "reward": 1,
            "passed": True,
            "provenance": {"commit_sha": "abc123"},
        }
    )
    assert measurements.total_tokens == 120
    assert measurements.runtime_sec == 4.5
    assert measurements.reward == 1.0
    assert measurements.passed is True
    assert measurements.provenance["commit_sha"] == "abc123"


def test_from_metadata_applies_fallbacks_and_ignores_bad_types() -> None:
    # duration_ms -> runtime_sec, passed -> reward, bool is not a token count.
    measurements = AttemptMeasurements.from_metadata(
        {"duration_ms": 2500, "passed": False, "total_tokens": True}
    )
    assert measurements.runtime_sec == 2.5
    assert measurements.reward == 0.0
    assert measurements.total_tokens is None

    empty = AttemptMeasurements.from_metadata(None)
    assert empty.reward is None and empty.runtime_sec is None and empty.provenance == {}


def test_to_metadata_round_trips_only_set_values() -> None:
    payload = AttemptMeasurements(total_tokens=10, runtime_sec=1.0, reward=1.0).to_metadata()
    assert payload == {"total_tokens": 10, "runtime_sec": 1.0, "reward": 1.0}
