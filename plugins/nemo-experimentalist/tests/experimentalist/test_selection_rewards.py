# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist.components.models import (
    INSIGHT_REWARD_PREFIX,
    pareto_front,
    selection_rewards,
)


def _candidate(
    label: str,
    *,
    validation_reward: dict[str, float] | None = None,
    insight_validation_reward: dict[str, float] | None = None,
    insight_train_reward: dict[str, float] | None = None,
) -> Candidate:
    return Candidate(
        run_id="run-1",
        label=label,
        round=1,
        optimization="baseline",
        validation_reward=validation_reward,
        insight_validation_reward=insight_validation_reward,
        insight_train_reward=insight_train_reward,
    )


def _front(candidates: list[Candidate]) -> set[str]:
    rewards = selection_rewards(candidates)
    return {candidate.label for candidate in pareto_front(candidates, lambda c: rewards[c.label])}


def test_insight_validation_dimensions_are_namespaced_beside_validation_reward() -> None:
    candidate = _candidate(
        "agent-0",
        validation_reward={"reward": 0.5, "uses_required_tool": 0.4},
        insight_validation_reward={"uses_required_tool": 0.9},
    )

    assert selection_rewards([candidate])["agent-0"] == {
        "reward": 0.5,
        "uses_required_tool": 0.4,
        f"{INSIGHT_REWARD_PREFIX}uses_required_tool": 0.9,
    }


def test_the_train_half_never_reaches_selection() -> None:
    candidate = _candidate(
        "agent-0",
        validation_reward={"reward": 0.5},
        insight_train_reward={"uses_required_tool": 1.0},
    )

    assert selection_rewards([candidate])["agent-0"] == {"reward": 0.5}


def test_missing_insight_scores_are_zero_filled_across_the_ranked_set() -> None:
    scored = _candidate(
        "agent-scored",
        validation_reward={"reward": 0.5},
        insight_validation_reward={"uses_required_tool": 0.8},
    )
    unscored = _candidate("agent-unscored", validation_reward={"reward": 0.5})

    rewards = selection_rewards([scored, unscored])

    assert rewards["agent-unscored"] == {"reward": 0.5, f"{INSIGHT_REWARD_PREFIX}uses_required_tool": 0.0}
    # Without the zero-fill the two key sets would differ and _dominates would call them
    # incomparable, leaving the strictly worse candidate on the front.
    assert _front([scored, unscored]) == {"agent-scored"}


def test_unscored_candidates_stay_incomparable_rather_than_dominated() -> None:
    scored = _candidate(
        "agent-scored",
        validation_reward={"reward": 0.9},
        insight_validation_reward={"uses_required_tool": 0.9},
    )
    pending = _candidate("agent-pending", insight_validation_reward={"uses_required_tool": 0.1})

    assert selection_rewards([scored, pending])["agent-pending"] == {}
    assert _front([scored, pending]) == {"agent-scored", "agent-pending"}


def test_a_candidate_strong_only_on_insight_dimensions_survives() -> None:
    generalist = _candidate(
        "agent-generalist",
        validation_reward={"reward": 0.9},
        insight_validation_reward={"uses_required_tool": 0.1},
    )
    specialist = _candidate(
        "agent-specialist",
        validation_reward={"reward": 0.4},
        insight_validation_reward={"uses_required_tool": 1.0},
    )

    assert _front([generalist, specialist]) == {"agent-generalist", "agent-specialist"}


def test_a_candidate_worse_on_every_merged_dimension_is_dominated() -> None:
    better = _candidate(
        "agent-better",
        validation_reward={"reward": 0.9},
        insight_validation_reward={"uses_required_tool": 0.9},
    )
    worse = _candidate(
        "agent-worse",
        validation_reward={"reward": 0.4},
        insight_validation_reward={"uses_required_tool": 0.1},
    )

    assert _front([better, worse]) == {"agent-better"}


def test_an_insight_only_regression_is_enough_to_be_dominated() -> None:
    """Insight validation is a real selection axis, not a tie-break on validation reward."""
    better = _candidate(
        "agent-better",
        validation_reward={"reward": 0.5},
        insight_validation_reward={"uses_required_tool": 0.9},
    )
    worse = _candidate(
        "agent-worse",
        validation_reward={"reward": 0.5},
        insight_validation_reward={"uses_required_tool": 0.2},
    )

    assert _front([better, worse]) == {"agent-better"}


def test_a_same_named_metric_on_both_splits_stays_on_two_axes() -> None:
    """The prefix keeps an Insight score from overwriting the validation score it shares a name with."""
    validation_specialist = _candidate(
        "agent-validation",
        validation_reward={"uses_required_tool": 0.9},
        insight_validation_reward={"uses_required_tool": 0.1},
    )
    insight_specialist = _candidate(
        "agent-insight",
        validation_reward={"uses_required_tool": 0.1},
        insight_validation_reward={"uses_required_tool": 0.9},
    )

    assert _front([validation_specialist, insight_specialist]) == {"agent-validation", "agent-insight"}
