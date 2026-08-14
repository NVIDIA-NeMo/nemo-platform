# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin how the run's winner is chosen at finalization.

This had no coverage, and a regression shipped through the gap: finalization was
routed through survivor selection, whose prompt requires including a candidate
created in the current round. At ``k=1`` that rule takes the only slot, so the
generation-0 baseline could never win and every run shipped a diff -- including runs
where nothing measured better than doing nothing.

M1 makes that structurally impossible by giving the selector two separate methods:
``survivors`` is the LLM judgement that must favour new blood, ``winner`` is
arithmetic that must not. These tests pin ``winner``.

The rule they encode: a candidate that regresses a protected metric is dropped, the
winner is non-dominated on the objectives, and among candidates nothing dominates,
the oldest wins. A real improvement dominates its ancestor and removes it from the
front, so the age preference only ever decides ties.
"""

from __future__ import annotations

import pytest
from nemo_experimentalist_plugin.entities import Candidate, MetricTarget, Proposal, ResourceRef, RewardRecord
from nemo_experimentalist_plugin.experimentalist.components.selector import ParetoDiversitySelector

MAXIMIZE = [MetricTarget(name="reward", direction="maximize")]
TWO_OBJECTIVES = [
    MetricTarget(name="reward", direction="maximize"),
    MetricTarget(name="shape_ok", direction="maximize"),
]
LATENCY_MUST_NOT_RISE = [MetricTarget(name="latency", direction="minimize")]
SHAPE_MUST_NOT_FALL = [MetricTarget(name="shape_ok", direction="maximize")]


def _candidate(label: str, generation: int, **metrics: float) -> Candidate:
    description = "baseline" if generation == 0 else "some change"
    return Candidate(
        run_id="run-1",
        label=label,
        generation=generation,
        description=description,
        generated_from=Proposal(ancestor=None, description=description, kind="import"),
        artifact=ResourceRef(uri=f"file:///tmp/{label}"),
        rewards={"validation": RewardRecord(metrics=dict(metrics))},
    )


def _killed(candidate: Candidate, generation: int) -> Candidate:
    candidate.killed_generation = generation
    return candidate


def _winner(
    candidates: list[Candidate],
    objectives: list[MetricTarget],
    regressions: list[MetricTarget] | None = None,
) -> Candidate | None:
    """Ask a real selector, so the wiring from config to component is covered too."""
    selector = ParetoDiversitySelector(objective_metrics=objectives, regression_metrics=regressions or [])
    return selector.winner(candidates)


def test_baseline_wins_a_tie() -> None:
    """The regression this file exists for: equal score means the diff bought nothing."""
    winner = _winner([_candidate("agent-0", 0, reward=0.5), _candidate("agent-1", 1, reward=0.5)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-0"


def test_baseline_wins_a_tie_regardless_of_input_order() -> None:
    """The old behaviour was correct only because agent-0 happened to be inserted first."""
    winner = _winner([_candidate("agent-1", 1, reward=0.5), _candidate("agent-0", 0, reward=0.5)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-0"


def test_a_real_improvement_wins() -> None:
    """Age must never block a candidate that actually scored better."""
    winner = _winner([_candidate("agent-0", 0, reward=0.5), _candidate("agent-1", 1, reward=0.7)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-1"


def test_a_regression_loses() -> None:
    winner = _winner([_candidate("agent-0", 0, reward=0.5), _candidate("agent-1", 1, reward=0.3)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-0"


def test_oldest_ancestor_wins_among_tied_descendants() -> None:
    """Not just the baseline: an ancestor carried forward unchanged also outranks a tie."""
    winner = _winner(
        [
            _candidate("agent-3", 3, reward=0.8),
            _candidate("agent-1", 1, reward=0.8),
            _candidate("agent-2", 2, reward=0.8),
        ],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_incomparable_multi_objective_candidate_does_not_displace_the_baseline() -> None:
    """Better on one objective and worse on another is not an improvement, it is a trade."""
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, shape_ok=0.9),
            _candidate("agent-1", 1, reward=0.7, shape_ok=0.4),
        ],
        TWO_OBJECTIVES,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_dominating_on_every_objective_wins() -> None:
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, shape_ok=0.5),
            _candidate("agent-1", 1, reward=0.7, shape_ok=0.9),
        ],
        TWO_OBJECTIVES,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_minimized_objective_direction_is_respected() -> None:
    winner = _winner(
        [_candidate("agent-0", 0, latency=2.0), _candidate("agent-1", 1, latency=1.0)],
        [MetricTarget(name="latency", direction="minimize")],
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_no_eligible_candidates_returns_none() -> None:
    assert _winner([], MAXIMIZE) is None


def test_a_candidate_without_the_objective_dimensions_is_not_eligible() -> None:
    """It cannot be ranked, so it cannot win -- and must not crash the finalizer."""
    assert _winner([_candidate("agent-0", 0, unrelated=1.0)], MAXIMIZE) is None


def test_single_candidate_is_the_winner() -> None:
    winner = _winner([_candidate("agent-1", 1, reward=0.7)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-1"


def test_same_generation_ties_are_stable_under_input_order() -> None:
    forward = _winner(
        [_candidate("agent-1", 1, reward=0.7), _candidate("agent-2", 1, reward=0.7)],
        MAXIMIZE,
    )
    backward = _winner(
        [_candidate("agent-2", 1, reward=0.7), _candidate("agent-1", 1, reward=0.7)],
        MAXIMIZE,
    )
    assert forward is not None and backward is not None
    assert forward.label == backward.label == "agent-1"


def test_creation_order_is_numeric_not_lexicographic() -> None:
    """``agent-10`` sorts before ``agent-9`` as text, and after it as a sequence."""
    winner = _winner(
        [_candidate("agent-10", 1, reward=0.7), _candidate("agent-9", 1, reward=0.7)],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-9"


def test_objective_gain_cannot_pay_for_a_regression() -> None:
    """A protected metric that worsens disqualifies the candidate however good the objective."""
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, latency=1.0),
            _candidate("agent-1", 1, reward=0.9, latency=2.5),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_improvement_that_holds_the_protected_metric_still_wins() -> None:
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, latency=1.0),
            _candidate("agent-1", 1, reward=0.9, latency=1.0),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_maximized_regression_metric_uses_the_opposite_direction() -> None:
    """``shape_ok`` must not *fall*; a candidate that improves reward but drops it is out."""
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, shape_ok=1.0),
            _candidate("agent-1", 1, reward=0.9, shape_ok=0.6),
        ],
        MAXIMIZE,
        SHAPE_MUST_NOT_FALL,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_multiple_objectives_and_a_regression_metric_together() -> None:
    """agent-1 dominates on both objectives but regresses latency; agent-2 is the honest win."""
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, shape_ok=0.5, latency=1.0),
            _candidate("agent-1", 1, reward=0.9, shape_ok=0.9, latency=3.0),
            _candidate("agent-2", 1, reward=0.7, shape_ok=0.7, latency=0.8),
        ],
        TWO_OBJECTIVES,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-2"


def test_every_candidate_regressing_falls_back_to_the_baseline() -> None:
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, latency=1.0),
            _candidate("agent-1", 1, reward=0.9, latency=2.0),
            _candidate("agent-2", 1, reward=0.8, latency=1.5),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_a_regression_metric_missing_from_a_candidate_is_not_a_regression() -> None:
    """Absent evidence must not disqualify: the evaluator simply did not report it."""
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5, latency=1.0),
            _candidate("agent-1", 1, reward=0.9),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_a_baseline_killed_mid_loop_can_still_win() -> None:
    """Survivor selection may kill agent-0; deciding to ship nothing must survive that.

    ``winner`` filters on ``killed_generation``, so without re-admitting the baseline a
    run whose baseline was killed could only choose among diffs -- reintroducing the very
    bug this module exists to prevent, one level down.
    """
    winner = _winner(
        [
            _killed(_candidate("agent-0", 0, reward=0.5), 1),
            _candidate("agent-1", 1, reward=0.5),
        ],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_regression_is_measured_against_the_real_baseline_not_the_oldest_survivor() -> None:
    """A killed baseline must still anchor the regression comparison.

    Against agent-1 (the oldest *survivor*) agent-2's latency of 2.5 is only a little
    worse; against the real baseline at 1.0 both candidates plainly regress.
    """
    winner = _winner(
        [
            _killed(_candidate("agent-0", 0, reward=0.5, latency=1.0), 1),
            _candidate("agent-1", 1, reward=0.7, latency=2.0),
            _candidate("agent-2", 2, reward=0.9, latency=2.5),
        ],
        MAXIMIZE,
        LATENCY_MUST_NOT_RISE,
    )
    assert winner is not None
    assert winner.label == "agent-0"


def test_a_killed_non_baseline_candidate_cannot_win() -> None:
    """Only the baseline is re-admitted; an eliminated diff stays eliminated."""
    winner = _winner(
        [
            _candidate("agent-0", 0, reward=0.5),
            _candidate("agent-1", 1, reward=0.7),
            _killed(_candidate("agent-2", 1, reward=0.9), 1),
        ],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_a_baseline_missing_the_objective_dimensions_is_not_used_as_reference() -> None:
    """It cannot be ranked, so it cannot anchor; the selector falls back rather than crash."""
    winner = _winner(
        [
            _candidate("agent-0", 0, unrelated=1.0),
            _candidate("agent-1", 1, reward=0.7),
        ],
        MAXIMIZE,
    )
    assert winner is not None
    assert winner.label == "agent-1"


def test_a_run_with_no_baseline_result_still_finalizes() -> None:
    winner = _winner([_candidate("agent-1", 1, reward=0.7)], MAXIMIZE)
    assert winner is not None
    assert winner.label == "agent-1"


@pytest.mark.parametrize("regressions", [None, LATENCY_MUST_NOT_RISE])
def test_the_default_objective_is_reward(regressions: list[MetricTarget] | None) -> None:
    """A selector built with no targets still ranks, so an unconfigured run finalizes."""
    selector = ParetoDiversitySelector(regression_metrics=regressions or [])
    winner = selector.winner([_candidate("agent-0", 0, reward=0.5), _candidate("agent-1", 1, reward=0.9)])
    assert winner is not None
    assert winner.label == "agent-1"
