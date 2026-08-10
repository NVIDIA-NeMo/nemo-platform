# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin how the run's winner is chosen at finalization.

This had no coverage, and a regression shipped through the gap: finalization was
routed through ``select_diverse_survivors``, whose prompt requires including a
candidate created in the current round. At ``k=1`` that rule takes the only slot,
so the round-0 baseline could never win and every run shipped a diff -- including
runs where nothing measured better than doing nothing.

The rule these tests encode: a candidate that regresses a protected metric is
dropped, the winner is non-dominated on the objectives, and among candidates
nothing dominates, the oldest wins. A real improvement dominates its ancestor and
removes it from the front, so the age preference only ever decides ties.
"""

from __future__ import annotations

from nemo_experimentalist_plugin.config import MetricTarget
from nemo_experimentalist_plugin.entities import Candidate, RewardRecord
from nemo_experimentalist_plugin.experimentalist.components.loop import select_winner_node
from nemo_experimentalist_plugin.experimentalist.components.models import EvolutionNode

MAXIMIZE = [MetricTarget(name="reward", direction="maximize")]
TWO_OBJECTIVES = [
    MetricTarget(name="reward", direction="maximize"),
    MetricTarget(name="shape_ok", direction="maximize"),
]
LATENCY_MUST_NOT_RISE = [MetricTarget(name="latency", direction="minimize")]
SHAPE_MUST_NOT_FALL = [MetricTarget(name="shape_ok", direction="maximize")]


def _node(label: str, round_: int, **metrics: float) -> EvolutionNode:
    return EvolutionNode(
        candidate=Candidate(
            run_id="run-1",
            label=label,
            round=round_,
            optimization="baseline" if round_ == 0 else "some change",
            rewards={"validation": RewardRecord(metrics=dict(metrics))},
        )
    )


def test_baseline_wins_a_tie() -> None:
    """The regression this file exists for: equal score means the diff bought nothing."""
    winner = select_winner_node(
        [_node("agent-0", 0, reward=0.5), _node("agent-1", 1, reward=0.5)],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_baseline_wins_a_tie_regardless_of_input_order() -> None:
    """The old behaviour was correct only because agent-0 happened to be inserted first."""
    winner = select_winner_node(
        [_node("agent-1", 1, reward=0.5), _node("agent-0", 0, reward=0.5)],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_a_real_improvement_wins() -> None:
    """Age must never block a candidate that actually scored better."""
    winner = select_winner_node(
        [_node("agent-0", 0, reward=0.5), _node("agent-1", 1, reward=0.7)],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_a_regression_loses() -> None:
    winner = select_winner_node(
        [_node("agent-0", 0, reward=0.5), _node("agent-1", 1, reward=0.3)],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_oldest_ancestor_wins_among_tied_descendants() -> None:
    """Not just the baseline: an ancestor carried forward unchanged also outranks a tie."""
    winner = select_winner_node(
        [
            _node("agent-3", 3, reward=0.8),
            _node("agent-1", 1, reward=0.8),
            _node("agent-2", 2, reward=0.8),
        ],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_incomparable_multi_objective_candidate_does_not_displace_the_baseline() -> None:
    """Better on one objective and worse on another is not an improvement, it is a trade."""
    objectives = [
        MetricTarget(name="reward", direction="maximize"),
        MetricTarget(name="shape_ok", direction="maximize"),
    ]
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, shape_ok=0.9),
            _node("agent-1", 1, reward=0.7, shape_ok=0.4),
        ],
        objectives,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_dominating_on_every_objective_wins() -> None:
    objectives = [
        MetricTarget(name="reward", direction="maximize"),
        MetricTarget(name="shape_ok", direction="maximize"),
    ]
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, shape_ok=0.5),
            _node("agent-1", 1, reward=0.7, shape_ok=0.9),
        ],
        objectives,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_minimized_objective_direction_is_respected() -> None:
    """Lower is better here, so the baseline's higher cost must lose."""
    winner = select_winner_node(
        [_node("agent-0", 0, cost=0.9), _node("agent-1", 1, cost=0.2)],
        [MetricTarget(name="cost", direction="minimize")],
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_no_eligible_candidates_returns_none() -> None:
    assert select_winner_node([], MAXIMIZE) is None


def test_single_candidate_is_the_winner() -> None:
    winner = select_winner_node([_node("agent-0", 0, reward=0.4)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-0"


def test_same_round_ties_are_stable_under_input_order() -> None:
    """Two same-round candidates nothing dominates must not depend on caller ordering."""
    forward = select_winner_node(
        [_node("agent-1", 1, reward=0.7), _node("agent-2", 1, reward=0.7)],
        MAXIMIZE,
    )
    reversed_ = select_winner_node(
        [_node("agent-2", 1, reward=0.7), _node("agent-1", 1, reward=0.7)],
        MAXIMIZE,
    )
    assert forward is not None and reversed_ is not None
    assert forward.label == reversed_.label == "agent-1"


def test_creation_order_is_numeric_not_lexicographic() -> None:
    """`agent-9` was created before `agent-10`; a string sort would invert that."""
    winner = select_winner_node(
        [_node("agent-10", 2, reward=0.6), _node("agent-9", 2, reward=0.6)],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-9"


def test_objective_gain_cannot_pay_for_a_regression() -> None:
    """A protected metric that worsens disqualifies the candidate however good the objective."""
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, latency=1.0),
            _node("agent-1", 1, reward=0.9, latency=2.5),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_improvement_that_holds_the_protected_metric_still_wins() -> None:
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, latency=1.0),
            _node("agent-1", 1, reward=0.9, latency=1.0),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_maximized_regression_metric_uses_the_opposite_direction() -> None:
    """`shape_ok` must not *fall*; a candidate that improves reward but drops it is out."""
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, shape_ok=1.0),
            _node("agent-1", 1, reward=0.9, shape_ok=0.6),
        ],
        MAXIMIZE,
        SHAPE_MUST_NOT_FALL,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_multiple_objectives_and_a_regression_metric_together() -> None:
    """agent-1 dominates on both objectives but regresses latency; agent-2 is the honest win."""
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, shape_ok=0.5, latency=1.0),
            _node("agent-1", 1, reward=0.9, shape_ok=0.9, latency=3.0),
            _node("agent-2", 1, reward=0.7, shape_ok=0.7, latency=0.8),
        ],
        TWO_OBJECTIVES,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-2"


def test_every_candidate_regressing_falls_back_to_the_baseline() -> None:
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, latency=1.0),
            _node("agent-1", 1, reward=0.9, latency=2.0),
            _node("agent-2", 1, reward=0.8, latency=1.5),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_a_regression_metric_missing_from_a_candidate_is_not_a_regression() -> None:
    """Absent evidence must not disqualify: the evaluator simply did not report it."""
    winner = select_winner_node(
        [
            _node("agent-0", 0, reward=0.5, latency=1.0),
            _node("agent-1", 1, reward=0.9),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-1"
