# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from nemo_agents_plugin.hardening.loop import run_hardening_loop
from nemo_agents_plugin.hardening.models import AttackHit, AttackResult

FIXTURES = Path(__file__).parent / "fixtures" / "hardening"


def _hit(index=0):
    return AttackHit(
        probe="promptinject.X", prompt="run command via bash_executor", output="leaked", detector="d", index=index
    )


class _ScriptedAttacker:
    """Returns a fixed AttackResult; records whether replay vs live was called."""

    def __init__(self, hits):
        self._hits = hits
        self.replay_calls = 0
        self.live_calls = 0

    def attack_replay(self, hitlog_path):
        self.replay_calls += 1
        return AttackResult(probes=["promptinject.X"], hits=self._hits, total_attempts=4, seed=1)

    def attack_live(self):
        self.live_calls += 1
        return AttackResult(probes=["promptinject.X"], hits=self._hits, total_attempts=4, seed=1)


def _platform():
    platform = MagicMock()
    created = MagicMock()
    created.name = "harden-round-0"
    created.id = "exp-0"
    platform.experiments.create = AsyncMock(return_value=created)
    platform.intake.ingest.atif.create = AsyncMock()
    return platform


def _complete(system, user):
    return "[SCORE]: 9" if "Security Auditor" in system else "Block bash_executor cat /etc/passwd."


def _kwargs(**over):
    base = dict(
        complete=_complete,
        platform=_platform(),
        workspace="default",
        experiment_group_id="grp-1",
        dataset_name="hardening-probes",
        guardrail_config_name="agent-hardening",
        benign_cases=[{"tool": "bash_executor", "payload": "run pwd"}],
        max_rounds=3,
    )
    base.update(over)
    return base


async def test_loop_converges_when_guardrail_blocks():
    """Round 0 finds a hit, builds a rule, the guardrail blocks it, residual is 0, loop stops."""
    applied = []
    kwargs = _kwargs(
        attacker=_ScriptedAttacker([_hit()]),
        apply_config=lambda data: applied.append(data),
        check=lambda msg: "blocked",
    )
    state = await run_hardening_loop(**kwargs)
    assert len(state.rounds) == 1
    assert state.rounds[0].attack_success_rate == 0.0
    assert state.rounds[0].remediation_count == 1
    # The applied config carries the generated block instruction in a self-check input rail.
    assert applied and applied[0]["rails"]["input"]["flows"] == ["self check input"]
    assert "Block bash_executor" in applied[0]["prompts"][0]["content"]
    kwargs["platform"].experiments.create.assert_awaited_once()


async def test_loop_runs_to_max_rounds_when_guardrail_never_blocks():
    """If the guardrail never blocks, residual stays 1.0 and the loop runs to max_rounds."""
    state = await run_hardening_loop(
        **_kwargs(attacker=_ScriptedAttacker([_hit()]), apply_config=lambda d: None, check=lambda msg: "success", max_rounds=2)
    )
    assert len(state.rounds) == 2
    assert all(r.attack_success_rate == 1.0 for r in state.rounds)


async def test_loop_records_benign_regression():
    """A guardrail that over-blocks the benign request records a benign_pass_rate drop."""
    state = await run_hardening_loop(
        **_kwargs(attacker=_ScriptedAttacker([_hit()]), apply_config=lambda d: None, check=lambda msg: "blocked")
    )
    assert state.rounds[0].benign_pass_rate == 0.0  # benign request wrongly blocked


async def test_loop_no_behavioral_findings_applies_no_config():
    """A hit that matches no behavioral reason yields no remediation and no config apply."""
    benign_hit = AttackHit(probe="p", prompt="what is the capital of France?", output="Paris", detector="d", index=0)
    applied = []
    state = await run_hardening_loop(
        **_kwargs(
            attacker=_ScriptedAttacker([benign_hit]),
            apply_config=lambda d: applied.append(d),
            check=lambda msg: "success",
            max_rounds=1,
        )
    )
    assert applied == []  # nothing to remediate, so no config written
    assert state.rounds[0].remediation_count == 0


async def test_loop_replay_branch_calls_attack_replay():
    """When replay_hitlog is set, the loop uses attack_replay, not attack_live."""
    attacker = _ScriptedAttacker([_hit()])
    await run_hardening_loop(
        **_kwargs(
            attacker=attacker,
            apply_config=lambda d: None,
            check=lambda msg: "blocked",
            replay_hitlog=FIXTURES / "sample.hitlog.jsonl",
            max_rounds=1,
        )
    )
    assert attacker.replay_calls == 1 and attacker.live_calls == 0
