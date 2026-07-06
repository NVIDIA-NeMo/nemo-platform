# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The behavioral hardening loop: attack, analyze, remediate, verify, record.

Per round: attack (live or replay), classify behavioral findings, generate
guardrail block instructions for newly-found attacks, rebuild and apply the
managed GuardrailConfig (input rail), verify by replaying the attacks and a
benign suite through the guardrail check, and record the round to the
experiments API. Remediations accumulate across rounds so the config only grows.
Stop when the post-defense attack-success-rate hits zero or max_rounds is reached.

The guardrail apply and check are injected (``apply_config`` / ``check``) so the
loop stays pure and testable: the job wires them to the platform guardrail SDK.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from rich.console import Console

from nemo_agents_plugin.hardening.attack_analysis import extract_behavioral_findings
from nemo_agents_plugin.hardening.defender import build_remediation
from nemo_agents_plugin.hardening.guardrail_config import build_rails_config
from nemo_agents_plugin.hardening.models import GuardrailRemediation, HardeningRound, HardeningState
from nemo_agents_plugin.hardening.publish import publish_round
from nemo_agents_plugin.hardening.verify import replay_attacks, run_benign_suite

logger = logging.getLogger(__name__)
# The optimization run_loop narrates rounds via rich Console; match it so the
# "watch attack success rate fall round over round" journey has visible output.
console = Console()


async def run_hardening_loop(
    *,
    attacker: Any,
    complete: Callable[[str, str], str],
    apply_config: Callable[[dict], None],
    check: Callable[[str], str],
    platform: Any,
    workspace: str,
    experiment_group_id: str,
    dataset_name: str,
    guardrail_config_name: str,
    benign_cases: list[dict[str, Any]] | None = None,
    max_rounds: int = 3,
    replay_hitlog: Path | None = None,
) -> HardeningState:
    state = HardeningState(experiment_group_id=experiment_group_id, guardrail_config_name=guardrail_config_name)
    benign_cases = benign_cases or []
    remediations: list[GuardrailRemediation] = []
    seen_findings: set[str] = set()

    for round_index in range(max_rounds):
        attack = attacker.attack_replay(replay_hitlog) if replay_hitlog else attacker.attack_live()
        findings = extract_behavioral_findings(attack.hits)

        fresh = [f for f in findings if f.finding_id not in seen_findings]
        for f in fresh:
            seen_findings.add(f.finding_id)
        new_remediations = build_remediation(fresh, complete=complete)
        remediations.extend(new_remediations)

        if remediations:
            apply_config(build_rails_config(remediations))

        replay = replay_attacks(attack.hits, check)
        benign = run_benign_suite(benign_cases, check)
        # Post-defense attack success: attacks that still got through the guardrail.
        residual = 0.0 if replay.total == 0 else replay.failed / replay.total

        trajectories = [
            {"test_case_id": hit.probe, "steps": [{"source": "agent", "message": hit.output}]}
            for hit in attack.hits
        ] or [{"test_case_id": "no-hits", "steps": []}]

        experiment_name = await publish_round(
            platform,
            workspace=workspace,
            experiment_group_id=experiment_group_id,
            round_index=round_index,
            attack_success_rate=residual,
            benign_pass_rate=benign.pass_rate,
            dataset_name=dataset_name,
            trajectories=trajectories,
        )

        state.rounds.append(
            HardeningRound(
                index=round_index,
                attack_success_rate=residual,
                benign_pass_rate=benign.pass_rate,
                remediation_count=len(remediations),
                experiment_name=experiment_name,
            )
        )
        console.print(
            f"[bold]round {round_index}[/bold]: attack success {residual:.0%}, "
            f"benign pass {benign.pass_rate:.0%}, {len(remediations)} rule(s)"
        )
        logger.info(
            "round %d: attack_success_rate=%.3f benign_pass_rate=%.3f rules=%d",
            round_index, residual, benign.pass_rate, len(remediations),
        )
        if residual == 0.0:
            break

    return state
