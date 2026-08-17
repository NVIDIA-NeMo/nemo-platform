# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rendering paths of the evolution tree.

These were uncovered, so a bulk rename reached them and nothing failed until a live run
crashed in `to_markdown_table`. `EvolutionNode` is not a `Candidate`: it exposes
`train_reward` / `val_reward` / `trajectory_reward` properties that delegate. Calling the
`Candidate` accessors on a node raises `AttributeError`.
"""

import pytest
from doubles import make_candidate, seed_reward
from nemo_experimentalist_plugin.entities import RewardRecord
from nemo_experimentalist_plugin.experimentalist.components.models import EvolutionNode, EvolutionTree


def _node(label: str, *, round_num: int, train: dict[str, float], val: dict[str, float]) -> EvolutionNode:
    return EvolutionNode(
        candidate=make_candidate(
            run_id="run-1",
            label=label,
            generation=round_num,
            description="baseline" if round_num == 0 else "improve tool use",
            rewards={
                "train": RewardRecord(metrics=train),
                "validation": RewardRecord(metrics=val),
            },
        )
    )


def _tree() -> EvolutionTree:
    tree = EvolutionTree()
    tree.nodes = {
        "agent-0": _node("agent-0", round_num=0, train={"reward": 0.25}, val={"reward": 0.5}),
        "agent-1": _node("agent-1", round_num=1, train={"reward": 0.75}, val={"reward": 1.0}),
    }
    return tree


def test_markdown_table_renders_every_reward_dimension() -> None:
    table = _tree().to_markdown_table()

    assert table.split("\n") == [
        "| gen | agent | ancestor | type | train:reward | validation:reward | description |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| 0 | agent-0 | - | - | 0.25 | 0.50 | baseline |",
        "| 1 | agent-1 | - | - | 0.75 | 1.00 | improve tool use |",
    ]


def test_node_reward_str_renders_every_measured_channel() -> None:
    node = _node("agent-0", round_num=0, train={"reward": 0.25}, val={"reward": 0.5})

    rendered = node.reward_str

    assert "train[" in rendered
    assert "validation[" in rendered


def test_rendering_picks_up_an_unknown_channel_without_code_changes() -> None:
    """The point of the channel map: a new channel reaches the report unaided."""
    node = _node("agent-0", round_num=0, train={"reward": 0.25}, val={"reward": 0.5})
    seed_reward(node.candidate, "some-new-channel", RewardRecord(metrics={"score": 0.9}))
    tree = EvolutionTree()
    tree.nodes = {"agent-0": node}

    assert "some-new-channel[" in node.reward_str
    assert "some-new-channel:score" in tree.to_markdown_table()
    assert "0.90" in tree.to_markdown_table()


def test_the_tree_is_keyed_by_candidate_id_not_by_display_label() -> None:
    """Identity and the display handle are different strings, and only one is a key."""
    baseline = make_candidate(label="agent-0", generation=0)
    child = make_candidate(label="agent-1", ancestor=baseline.id, generation=1)
    tree = EvolutionTree.from_candidates([baseline, child])

    assert set(tree.nodes) == {baseline.id, child.id}
    assert tree.nodes[child.id].candidate is child


def test_marking_the_best_by_display_label_fails_loudly() -> None:
    """A silent no-op here surfaced one line later as an unrelated KeyError."""
    baseline = make_candidate(label="agent-0", generation=0)
    tree = EvolutionTree.from_candidates([baseline])

    tree.mark_best(baseline.id)
    assert tree.nodes[baseline.id].is_best

    with pytest.raises(KeyError, match="keys are candidate ids"):
        tree.mark_best("agent-0-that-is-a-label")
