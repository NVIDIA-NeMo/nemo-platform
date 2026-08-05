# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""What the Proposer must reject before its output reaches a Builder.

`ancestor` became a candidate id rather than a display handle, and survivors are handed
to the model carrying both — so a plausible-looking `"agent-2"` is exactly what comes
back. One rejected batch costs a retry; an unvalidated one costs the run, because the
fork that resolves it happens outside the per-proposal error handling.
"""

import pytest
from nemo_experimentalist_plugin.experimentalist.components.proposer import Improvement, Proposer


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
    usable = Proposer._usable_improvements(
        [_improvement("agent-2"), _improvement("id-agent-2", optimization_type="add_tool")],
        known_ancestors={"id-agent-2"},
        allowed_types={"add_method", "add_tool"},
    )

    assert [improvement.ancestor for improvement in usable] == ["id-agent-2"]


def test_a_real_survivor_id_passes() -> None:
    usable = Proposer._usable_improvements(
        [_improvement("id-agent-2")], known_ancestors={"id-agent-2"}, allowed_types={"add_method"}
    )

    assert len(usable) == 1
    Proposer._validate_improvements(improvements=usable, max_candidates=3)


def test_a_batch_where_every_ancestor_is_unknown_still_fails_loudly() -> None:
    """Dropping them all would leave the round silently proposing nothing."""
    with pytest.raises(ValueError, match="None of the Proposer's 1 improvements were usable"):
        Proposer._usable_improvements(
            [_improvement("agent-2")], known_ancestors={"id-agent-2"}, allowed_types={"add_method"}
        )


def test_a_near_miss_optimization_type_is_dropped_not_fatal() -> None:
    """`edit_method` for `edit_concrete_method` ended a real run at round two.

    There are twenty valid types, so a near miss is as likely as a wrong ancestor, and
    this check runs after the CodeAct loop where raising buys no retry.
    """
    usable = Proposer._usable_improvements(
        [_improvement("id-a", optimization_type="edit_method"), _improvement("id-a", optimization_type="add_method")],
        known_ancestors={"id-a"},
        allowed_types={"add_method", "edit_concrete_method"},
    )

    assert [improvement.optimization_type for improvement in usable] == ["add_method"]
