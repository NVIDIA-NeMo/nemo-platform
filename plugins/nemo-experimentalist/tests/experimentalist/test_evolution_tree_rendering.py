# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rendering paths of the evolution tree.

These were uncovered, so a bulk rename reached them and nothing failed until a live run
crashed in `to_markdown_table`. `EvolutionNode` is not a `Candidate`: it exposes
`train_reward` / `val_reward` / `trajectory_reward` properties that delegate. Calling the
`Candidate` accessors on a node raises `AttributeError`.
"""

from nemo_experimentalist_plugin.entities import Candidate, RewardRecord
from nemo_experimentalist_plugin.experimentalist.components.models import EvolutionNode, EvolutionTree


def _node(label: str, *, round_num: int, train: dict[str, float], val: dict[str, float]) -> EvolutionNode:
    return EvolutionNode(
        candidate=Candidate(
            run_id="run-1",
            label=label,
            round=round_num,
            optimization="baseline" if round_num == 0 else "improve tool use",
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
        "| round | agent | ancestor | type | train:reward | val:reward | optimization |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| 0 | agent-0 | - | - | 0.25 | 0.50 | baseline |",
        "| 1 | agent-1 | - | - | 0.75 | 1.00 | improve tool use |",
    ]


def test_node_reward_str_renders_every_measured_channel() -> None:
    node = _node("agent-0", round_num=0, train={"reward": 0.25}, val={"reward": 0.5})

    rendered = node.reward_str

    assert "train[" in rendered
    assert "val[" in rendered


def test_rendering_picks_up_an_unknown_channel_without_code_changes() -> None:
    """The point of the channel map: a new channel reaches the report unaided."""
    node = _node("agent-0", round_num=0, train={"reward": 0.25}, val={"reward": 0.5})
    node.candidate.record_reward("some-new-channel", metrics={"score": 0.9})
    tree = EvolutionTree()
    tree.nodes = {"agent-0": node}

    assert "some-new-channel[" in node.reward_str
    assert "some-new-channel:score" in tree.to_markdown_table()
    assert "0.90" in tree.to_markdown_table()
