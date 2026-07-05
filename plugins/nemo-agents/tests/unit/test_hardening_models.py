# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from nemo_agents_plugin.hardening.models import (
    AttackHit,
    AttackResult,
    BehavioralFinding,
    GuardrailRemediation,
    VerifyResult,
    HardeningRound,
    HardeningState,
    _serialize,
)


def test_attack_result_success_rate():
    """One hit in four attempts is a 0.25 attack-success-rate."""
    hits = [AttackHit(probe="promptinject.HijackHateHumans", prompt="p", output="o", detector="x", index=0)]
    result = AttackResult(probes=["promptinject.HijackHateHumans"], hits=hits, total_attempts=4, seed=1234)
    assert result.attack_success_rate == 0.25


def test_attack_result_zero_attempts_is_zero_rate():
    """Zero attempts must not divide by zero."""
    result = AttackResult(probes=[], hits=[], total_attempts=0, seed=1234)
    assert result.attack_success_rate == 0.0


def test_verify_result_pass_rate():
    """Nine of ten passing is a 0.9 pass-rate."""
    vr = VerifyResult(total=10, passed=9, failed=1, errored=0, detail=[])
    assert vr.pass_rate == 0.9


def test_verify_result_zero_total_is_zero_rate():
    """An empty suite reports 0.0, not a division error."""
    assert VerifyResult(total=0, passed=0, failed=0, errored=0, detail=[]).pass_rate == 0.0


def test_guardrail_remediation_defaults_to_input_rail():
    """A remediation lands on the input rail by default."""
    r = GuardrailRemediation(finding_id="attack-0000", attack_prompt="p", victim_response="o", guardrail_prompt="block")
    assert r.rail_type == "input"


def test_hardening_state_appends_rounds_and_serializes():
    """_serialize turns nested dataclasses into plain JSON-able dicts."""
    state = HardeningState()
    state.rounds.append(
        HardeningRound(
            index=0,
            attack_success_rate=0.5,
            benign_pass_rate=1.0,
            remediation_count=2,
            experiment_name="harden-round-0",
        )
    )
    blob = _serialize(state)
    assert blob["rounds"][0]["attack_success_rate"] == 0.5
    assert blob["rounds"][0]["experiment_name"] == "harden-round-0"


def test_serialize_ignores_unrelated_finding_type():
    """BehavioralFinding serializes its tuple reasons to a list."""
    f = BehavioralFinding(
        finding_id="attack-0000", attack_index=0, record_index=None, text="t", record={}, guardrails_reasons=("a", "b")
    )
    assert _serialize(f)["guardrails_reasons"] == ["a", "b"]
