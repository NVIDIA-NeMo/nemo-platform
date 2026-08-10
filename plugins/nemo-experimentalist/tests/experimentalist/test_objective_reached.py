# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin when a solved objective ends a run.

Before this, the only stop conditions were the round budget and a stagnation
judgement. Neither notices success: a round that goes 0.333 -> 1.000 is the
clearest possible case of *not* stagnating, so a solved run kept buying rounds
that could only match what it already had.

The rule: when every objective carrying a ``target`` is satisfied by a candidate
that could win, stop. Absent targets, nothing changes.
"""

from __future__ import annotations

import pytest
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig, MetricTarget
from nemo_experimentalist_plugin.entities import Candidate, RewardRecord
from nemo_experimentalist_plugin.experimentalist.components.models import EvolutionNode, EvolutionTree
from nemo_experimentalist_plugin.experimentalist.components.terminator import Terminator

SOLVED = [MetricTarget(name="reward", direction="maximize", target=1.0)]
UNTARGETED = [MetricTarget(name="reward", direction="maximize")]


def _node(label: str, round_: int, killed: int | None = None, **metrics: float) -> EvolutionNode:
    candidate = Candidate(
        run_id="run-1",
        label=label,
        round=round_,
        optimization="baseline" if round_ == 0 else "some change",
        rewards={"validation": RewardRecord(metrics=dict(metrics))},
    )
    candidate.killed_round = killed
    return EvolutionNode(candidate=candidate)


def _tree(*nodes: EvolutionNode) -> EvolutionTree:
    tree = EvolutionTree()
    for node in nodes:
        tree.add(node.candidate)
    return tree


def _assess(tree: EvolutionTree, objectives: list[MetricTarget], **overrides: object):
    config = EvolutionaryOptimizerConfig.model_validate(
        {"objective_function": [target.model_dump() for target in objectives], **overrides}
    )
    return Terminator.assess_objective_reached(Terminator, evolution_tree=tree, config=config)  # type: ignore[arg-type]


def test_a_solved_objective_stops_the_run() -> None:
    decision = _assess(_tree(_node("agent-0", 0, reward=0.333), _node("agent-1", 1, reward=1.0)), SOLVED)
    assert decision.stop
    assert "agent-1" in decision.reason


def test_an_unsolved_objective_does_not_stop_the_run() -> None:
    decision = _assess(_tree(_node("agent-0", 0, reward=0.333), _node("agent-1", 1, reward=0.667)), SOLVED)
    assert not decision.stop


def test_no_target_configured_never_stops() -> None:
    """Absent an explicit target there is no value that means 'as good as possible'."""
    decision = _assess(_tree(_node("agent-0", 0, reward=1.0), _node("agent-1", 1, reward=1.0)), UNTARGETED)
    assert not decision.stop


def test_a_baseline_that_already_meets_the_target_stops_before_any_round() -> None:
    """The terminator is consulted at the top of round 1, so nothing is paid for."""
    decision = _assess(_tree(_node("agent-0", 0, reward=1.0)), SOLVED)
    assert decision.stop
    assert "agent-0" in decision.reason


def test_every_targeted_objective_must_be_met() -> None:
    objectives = [
        MetricTarget(name="reward", direction="maximize", target=1.0),
        MetricTarget(name="shape_ok", direction="maximize", target=1.0),
    ]
    partial = _assess(_tree(_node("agent-1", 1, reward=1.0, shape_ok=0.5)), objectives)
    assert not partial.stop
    both = _assess(_tree(_node("agent-1", 1, reward=1.0, shape_ok=1.0)), objectives)
    assert both.stop


def test_an_untargeted_objective_does_not_block_the_stop() -> None:
    """Only targeted objectives are judged; an untargeted one is not an obstacle."""
    objectives = [
        MetricTarget(name="reward", direction="maximize", target=1.0),
        MetricTarget(name="coverage", direction="maximize"),
    ]
    decision = _assess(_tree(_node("agent-1", 1, reward=1.0, coverage=0.1)), objectives)
    assert decision.stop


def test_minimized_objective_uses_the_opposite_comparison() -> None:
    objectives = [MetricTarget(name="cost", direction="minimize", target=0.2)]
    assert _assess(_tree(_node("agent-1", 1, cost=0.1)), objectives).stop
    assert not _assess(_tree(_node("agent-1", 1, cost=0.3)), objectives).stop


def test_a_missing_measurement_is_not_success() -> None:
    """The metric was never reported; absence must not be read as meeting the target."""
    decision = _assess(_tree(_node("agent-1", 1, other=1.0)), SOLVED)
    assert not decision.stop


def test_a_killed_candidate_cannot_end_the_run() -> None:
    """It cannot win, so stopping on it would ship a winner that never met the target."""
    decision = _assess(
        _tree(_node("agent-0", 0, reward=0.333), _node("agent-1", 1, killed=1, reward=1.0)),
        SOLVED,
    )
    assert not decision.stop


def test_a_killed_baseline_still_counts() -> None:
    """Finalization re-admits the baseline, so it remains a candidate for winning."""
    decision = _assess(_tree(_node("agent-0", 0, killed=1, reward=1.0)), SOLVED)
    assert decision.stop


def test_unscored_nodes_are_ignored() -> None:
    decision = _assess(_tree(_node("agent-0", 0, reward=0.5), _node("agent-1", 1)), SOLVED)
    assert not decision.stop


@pytest.mark.parametrize("disabled", [True, False])
def test_the_stop_is_independent_of_disable_convergence_check(disabled: bool) -> None:
    """That flag turns off a judgement about stagnation; this is a stated threshold."""
    decision = _assess(
        _tree(_node("agent-1", 1, reward=1.0)),
        SOLVED,
        disable_convergence_check=disabled,
    )
    assert decision.stop
