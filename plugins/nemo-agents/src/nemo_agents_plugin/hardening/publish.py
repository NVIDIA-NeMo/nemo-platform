# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Record a hardening round to the platform experiments API.

Mirrors nemo-evaluator's intake/publish.py: create one Experiment per round in a
shared ExperimentGroup, then ingest one ATIF trajectory per test case. Scores
ride inline on ``extra.verifier_result.rewards`` so Studio's leaderboard shows
``Avg attack_success_rate`` / ``Avg benign_pass_rate`` per round.
"""
from __future__ import annotations

from typing import Any

# Must be one of the SDK's accepted literals ("ATIF-v1.0".."ATIF-v1.7"); a bare
# "1.0" fails validation.
ATIF_SCHEMA_VERSION = "ATIF-v1.7"


def _with_step_ids(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every agent step carries the required ``step_id`` (AtifStepAgentParam)."""
    numbered = []
    for i, step in enumerate(steps):
        step = dict(step)
        step.setdefault("source", "agent")
        step.setdefault("step_id", i)
        numbered.append(step)
    return numbered


async def publish_round(
    platform: Any,
    *,
    workspace: str,
    experiment_group_id: str,
    round_index: int,
    attack_success_rate: float,
    benign_pass_rate: float,
    dataset_name: str,
    trajectories: list[dict[str, Any]],
) -> str:
    """Create the round's Experiment and ingest its trajectories with round scores.

    The Experiment is created before any ingest because intake rejects an unknown
    experiment_id with HTTP 400. Ingest failures propagate (no silent swallow).
    """
    experiment = await platform.experiments.create(
        workspace=workspace,
        name=f"harden-round-{round_index}",
        dataset_name=dataset_name,
        experiment_group_id=experiment_group_id,
    )
    rewards = {"attack_success_rate": attack_success_rate, "benign_pass_rate": benign_pass_rate}
    for trajectory in trajectories:
        body = {
            "workspace": workspace,
            "schema_version": ATIF_SCHEMA_VERSION,
            "agent": {"name": "agent-under-test", "version": "hardening"},
            "steps": _with_step_ids(trajectory.get("steps", [])),
            "experiment_context": {
                "experiment_id": experiment.id,
                "test_case_id": trajectory.get("test_case_id"),
            },
            "extra": {"verifier_result": {"rewards": rewards}},
        }
        await platform.intake.ingest.atif.create(**body)
    return experiment.name
