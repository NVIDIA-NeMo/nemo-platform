# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""What the Proposer must reject before its output reaches a Builder.

`ancestor` became a candidate id rather than a display handle, and survivors are handed
to the model carrying both — so a plausible-looking `"agent-2"` is exactly what comes
back. One rejected batch costs a retry; an unvalidated one costs the run, because the
fork that resolves it happens outside the per-proposal error handling.
"""

import pytest
from nemo_experimentalist_plugin.experimentalist.components.proposer import CodeChangeProposer, Improvement


def _improvement(ancestor: str, optimization_type: str = "add_method") -> Improvement:
    return Improvement(
        ancestor=ancestor,
        optimization="add a retrieval step",
        root_cause="the agent never retrieves",
        optimization_type=optimization_type,
        task_ids=["task-1"],
    )


def test_an_ancestor_that_is_not_a_survivor_id_is_dropped_not_fatal() -> None:
    """A label where an id belongs is one bad proposal, not a reason to end the run.

    This check runs after the CodeAct loop, so raising buys no retry — it unwinds through
    the strategy and fails a run that may have spent hours. The survivors carry both `id`
    and `label`, so "agent-2" is exactly what a model returns.
    """
    usable = CodeChangeProposer._usable_improvements(
        [_improvement("agent-2"), _improvement("id-agent-2", optimization_type="add_tool")],
        known_ancestors={"id-agent-2"},
        allowed_types={"add_method", "add_tool"},
    )

    assert [improvement.ancestor for improvement in usable] == ["id-agent-2"]


def test_a_real_survivor_id_passes() -> None:
    usable = CodeChangeProposer._usable_improvements(
        [_improvement("id-agent-2")], known_ancestors={"id-agent-2"}, allowed_types={"add_method"}
    )

    assert len(usable) == 1
    CodeChangeProposer._validate_improvements(improvements=usable, max_candidates=3)


def test_a_batch_where_every_ancestor_is_unknown_still_fails_loudly() -> None:
    """Dropping them all would leave the round silently proposing nothing."""
    with pytest.raises(ValueError, match="None of the Proposer's 1 improvements were usable"):
        CodeChangeProposer._usable_improvements(
            [_improvement("agent-2")], known_ancestors={"id-agent-2"}, allowed_types={"add_method"}
        )


def test_a_near_miss_optimization_type_is_dropped_not_fatal() -> None:
    """`edit_method` for `edit_concrete_method` ended a real run at round two.

    There are twenty valid types, so a near miss is as likely as a wrong ancestor, and
    this check runs after the CodeAct loop where raising buys no retry.
    """
    usable = CodeChangeProposer._usable_improvements(
        [_improvement("id-a", optimization_type="edit_method"), _improvement("id-a", optimization_type="add_method")],
        known_ancestors={"id-a"},
        allowed_types={"add_method", "edit_concrete_method"},
    )

    assert [improvement.optimization_type for improvement in usable] == ["add_method"]


def test_two_improvements_may_share_an_optimization_type() -> None:
    """#1163: a repeated type is not evidence of a malformed batch.

    There are twenty optimization types and two genuinely different edits to the same
    method share one, so raising here ends a paid-for round over nothing. A real
    duplicate is caught by the text check below instead. This killed a live
    generalization run, where the Proposer returned two distinct fixes both typed
    `edit_concrete_method`.
    """
    kept = CodeChangeProposer._validate_improvements(
        improvements=[
            _improvement("id-agent-0", optimization_type="edit_concrete_method"),
            Improvement(
                ancestor="id-agent-0",
                optimization="reorder the dispatch chain",
                root_cause="the list handler shadows the count handler",
                optimization_type="edit_concrete_method",
                task_ids=["task-2"],
            ),
        ],
        max_candidates=2,
    )

    assert [improvement.optimization for improvement in kept] == [
        "add a retrieval step",
        "reorder the dispatch chain",
    ]


def test_the_same_optimization_text_twice_is_dropped_to_one() -> None:
    """Identical text is a real duplicate: building it twice buys nothing."""
    kept = CodeChangeProposer._validate_improvements(
        improvements=[_improvement("id-agent-0"), _improvement("id-agent-0", optimization_type="add_tool")],
        max_candidates=2,
    )

    assert len(kept) == 1


def test_a_type_used_in_an_earlier_round_may_be_used_again() -> None:
    """#1163: novelty is a preference in the prompt, never an allowlist in the validator.

    `available_types` is `all_types - tried_types`, so enforcing it would forbid a type
    the moment it worked. A real multi-round run died on exactly that: rounds 1 and 2
    took the agent from 0.333 to 1.000 with `edit_concrete_method`, round 3 proposed
    refining it, and the only proposal was rejected as unusable -- which raises and ends
    a run mid-flight, precisely when the loop is succeeding.
    """
    all_types = {"add_method", "edit_concrete_method"}

    usable = CodeChangeProposer._usable_improvements(
        [_improvement("id-agent-0", optimization_type="edit_concrete_method")],
        known_ancestors={"id-agent-0"},
        allowed_types=all_types,  # the full vocabulary, not the untried remainder
    )

    assert [improvement.optimization_type for improvement in usable] == ["edit_concrete_method"]
