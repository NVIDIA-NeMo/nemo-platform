# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""End-to-end replay smoke test: real fixtures through the loop, boundaries stubbed."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nemo_agents_plugin.hardening.auditor_attack import AuditorAttacker
from nemo_agents_plugin.hardening.loop import run_hardening_loop

FIXTURES = Path(__file__).parent / "fixtures" / "hardening"


def _platform():
    platform = MagicMock()
    created = MagicMock()
    created.name = "harden-round-0"
    created.id = "exp-0"
    platform.experiments.create = AsyncMock(return_value=created)
    platform.intake.ingest.atif.create = AsyncMock()
    return platform


async def test_replay_smoke_generates_config_and_records_round():
    """Replaying the fixture hitlog runs the full loop: classify, remediate, apply, verify, record."""
    applied: list[dict] = []
    attacker = AuditorAttacker(
        _platform(),
        probe_spec="promptinject,dan.DanInTheWild",
        seed=1,
        target_type="nim",
        target_model="aut",
        target_options={"nim": {"uri": "http://x/v1"}},
        total_attempts=4,
    )

    state = await run_hardening_loop(
        attacker=attacker,
        complete=lambda system, user: "[SCORE]: 9" if "Security Auditor" in system else "Block this attack pattern.",
        apply_config=lambda data: applied.append(data),
        check=lambda msg: "blocked",  # the generated guardrail blocks the replayed attacks
        platform=_platform(),
        workspace="default",
        experiment_group_id="grp",
        dataset_name="hardening-probes",
        guardrail_config_name="agent-hardening",
        benign_cases=[{"tool": "bash_executor", "payload": "run pwd"}],
        max_rounds=1,
        replay_hitlog=FIXTURES / "sample.hitlog.jsonl",
    )

    assert len(state.rounds) == 1
    # Both fixture hits classified as behavioral, so two rules landed in the applied config.
    assert applied and applied[0]["rails"]["input"]["flows"] == ["self check input"]
    assert state.rounds[0].remediation_count == 2
    # Guardrail blocked the replayed attacks: post-defense attack success is zero.
    assert state.rounds[0].attack_success_rate == 0.0
