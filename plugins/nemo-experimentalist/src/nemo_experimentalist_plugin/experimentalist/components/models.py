# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core data models for the Experimentalist's optimization loop.

Ported from AAD ``skills/eval-and-optimize-base/scripts/optimizer/models.py``.
Pure data — no platform dependencies — shared vocabulary between the loop,
analyzer, proposer, coder, and evaluator.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal, TypeVar

from nemo_experimentalist_plugin.entities import Candidate
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Pareto utilities
# ---------------------------------------------------------------------------

T = TypeVar("T")


def _dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    """Return True iff *a* Pareto-dominates *b* on every shared dimension."""
    if not a or not b or a.keys() != b.keys():
        return False
    return all(a[k] >= b[k] for k in a) and any(a[k] > b[k] for k in a)


def pareto_front(
    items: Iterable[T],
    reward_of: Callable[[T], dict[str, float]],
) -> list[T]:
    """Return the non-dominated subset of *items*.

    Items with empty rewards are kept (incomparable, not dominated).
    """
    items = list(items)
    rewards = [reward_of(i) for i in items]
    front: list[T] = []
    for i, item in enumerate(items):
        if any(_dominates(rewards[j], rewards[i]) for j in range(len(items)) if j != i):
            continue
        front.append(item)
    return front


def pareto_sort(
    items: Iterable[T],
    reward_of: Callable[[T], dict[str, float]],
) -> list[T]:
    """Sort by non-domination rank (front 0 first, then front 1, …)."""
    remaining = list(items)
    out: list[T] = []
    while remaining:
        front = pareto_front(remaining, reward_of)
        out.extend(front)
        front_ids = {id(x) for x in front}
        remaining = [x for x in remaining if id(x) not in front_ids]
    return out


# ---------------------------------------------------------------------------
# OptimizationType
# ---------------------------------------------------------------------------

OptimizationType = Literal[
    # Edit existing elements
    "edit_method",
    "edit_concrete_method",
    "edit_skill",
    "edit_llm",
    "edit_config",
    # Add new elements
    "add_method",
    "add_concrete_method",
    "add_subagent",
    "add_tool",
    "add_llm",
    "add_skill",
    # Remove elements
    "remove_method",
    "remove_concrete_method",
    "remove_subagent",
    "remove_tool",
    "remove_llm",
    "remove_skill",
    # Structural transforms
    "split_method",
    "merge_method",
    # Method nature conversions
    "make_method_concrete",
    "make_method_abstract",
]


# ---------------------------------------------------------------------------
# Candidate helpers
# ---------------------------------------------------------------------------


def _format_reward(reward: dict[str, float]) -> str:
    if not reward:
        return "-"
    keys = ["aggregate"] if "aggregate" in reward else []
    keys.extend(k for k in sorted(reward) if k != "aggregate")
    return " ".join(f"{k}={reward[k]:.2f}" for k in keys)


# ---------------------------------------------------------------------------
# EvolutionNode
# ---------------------------------------------------------------------------


class EvolutionNode(BaseModel):
    """One node in the evolution tree, representing one Candidate."""

    candidate: Candidate
    is_best: bool = False

    @property
    def label(self) -> str:
        return self.candidate.label

    @property
    def ancestor(self) -> str | None:
        return self.candidate.ancestor

    @property
    def round(self) -> int:
        return self.candidate.round

    @property
    def optimization_type(self) -> str | None:
        return self.candidate.optimization_type

    @property
    def optimization(self) -> str:
        return self.candidate.optimization

    @property
    def train_reward(self) -> dict[str, float]:
        return self.candidate.train_reward or {}

    @property
    def val_reward(self) -> dict[str, float]:
        return self.candidate.validation_reward or {}

    @property
    def trajectory_reward(self) -> dict[str, float]:
        return self.candidate.validation_trajectory_reward or {}

    @property
    def is_survivor(self) -> bool:
        return self.candidate.killed_round is None

    @property
    def reward_str(self) -> str:
        parts = []
        if self.train_reward:
            parts.append(f"tr[{_format_reward(self.train_reward)}]")
        if self.val_reward:
            parts.append(f"val[{_format_reward(self.val_reward)}]")
        if self.trajectory_reward:
            parts.append(f"traj[{_format_reward(self.trajectory_reward)}]")
        return " ".join(parts) if parts else "no rewards"


# ---------------------------------------------------------------------------
# EvolutionTree
# ---------------------------------------------------------------------------


class EvolutionTree:
    """Tracks agent lineage and improvements across optimization rounds."""

    def __init__(self) -> None:
        self.nodes: dict[str, EvolutionNode] = {}
        self._children: dict[str, list[str]] = {}

    @classmethod
    def from_dir(cls, agents_dir: Path) -> EvolutionTree:
        """Rebuild the full tree from agent directories on disk."""
        tree = cls()
        if not agents_dir.exists():
            return tree
        for agent_dir in sorted(agents_dir.iterdir()):
            meta_path = agent_dir / "metadata.json"
            if not agent_dir.is_dir() or not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            candidate = Candidate.model_validate(meta)
            entity_id = meta.get("id", "")
            if entity_id:
                candidate._id = entity_id  # type: ignore[attr-defined]
            tree.add(candidate)
        return tree

    def survivors(self, max_round: int | None = None) -> list[Candidate]:
        """Return alive candidates up to *max_round* (or all if None)."""
        return [
            n.candidate for n in self.nodes.values() if n.is_survivor and (max_round is None or n.round <= max_round)
        ]

    def add(self, candidate: Candidate) -> EvolutionNode:
        """Add or update a candidate in the tree."""
        if candidate.label in self.nodes:
            node = self.nodes[candidate.label]
            node.candidate = candidate
            return node
        node = EvolutionNode(candidate=candidate)
        self.nodes[candidate.label] = node
        parent_key = candidate.ancestor or "__root__"
        self._children.setdefault(parent_key, []).append(candidate.label)
        return node

    def mark_best(self, label: str) -> None:
        """Designate the node with *label* as the best, clearing all other best flags."""
        for node in self.nodes.values():
            node.is_best = False
        if label in self.nodes:
            self.nodes[label].is_best = True

    def get_best(self) -> list[EvolutionNode]:
        """Return the Pareto-optimal nodes by validation reward."""
        scored = [n for n in self.nodes.values() if n.val_reward]
        if not scored:
            return []
        return pareto_front(scored, lambda n: n.val_reward)

    def to_markdown_table(self) -> str:
        """Export as a markdown table with all score dimensions as columns."""
        train_keys: set[str] = set()
        val_keys: set[str] = set()
        traj_keys: set[str] = set()
        for n in self.nodes.values():
            train_keys.update(n.train_reward.keys())
            val_keys.update(n.val_reward.keys())
            traj_keys.update(n.trajectory_reward.keys())
        train_cols = sorted(train_keys)
        val_cols = sorted(val_keys)
        traj_cols = sorted(traj_keys)

        fixed = ["round", "agent", "ancestor", "type"]
        all_cols = (
            fixed
            + [f"train:{k}" for k in train_cols]
            + [f"val:{k}" for k in val_cols]
            + [f"traj:{k}" for k in traj_cols]
            + ["optimization"]
        )
        header = "| " + " | ".join(all_cols) + " |"
        sep = "| " + " | ".join("---" for _ in all_cols) + " |"
        lines = [header, sep]

        for label in sorted(
            self.nodes.keys(),
            key=lambda x: int(x.split("-")[1]) if x.split("-")[-1].isdigit() else 0,
        ):
            n = self.nodes[label]
            train_vals = [f"{n.train_reward[k]:.2f}" if k in n.train_reward else "-" for k in train_cols]
            val_vals = [f"{n.val_reward[k]:.2f}" if k in n.val_reward else "-" for k in val_cols]
            traj_vals = [f"{n.trajectory_reward[k]:.2f}" if k in n.trajectory_reward else "-" for k in traj_cols]
            opt = (n.optimization or "")[:50].replace("\n", " ")
            cells = [
                str(n.round),
                n.label,
                n.ancestor or "-",
                n.optimization_type or "-",
            ]
            cells += [*train_vals, *val_vals, *traj_vals, opt]
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)

    def __repr__(self) -> str:
        if not self.nodes:
            return "EvolutionTree(empty)"
        lines = ["EvolutionTree:"]
        roots = sorted(set(self._children.get("__root__", []) + self._children.get("baseline", [])))
        if not roots:
            roots = [nid for nid, n in self.nodes.items() if n.ancestor is None or n.ancestor not in self.nodes]
        for i, root_id in enumerate(sorted(roots)):
            lines.extend(self._build_tree_lines(root_id, "", i == len(roots) - 1))
        return "\n".join(lines)

    def _render_node(self, node: EvolutionNode) -> str:
        opt_type = f"[{node.optimization_type}]" if node.optimization_type else ""
        opt_desc = (node.optimization or "")[:40].replace("\n", " ")
        if opt_desc and len(node.optimization) > 40:
            opt_desc += "..."
        markers = (" *BEST*" if node.is_best else "") + (" [S]" if node.is_survivor else "")
        return f"{node.label} ({node.reward_str}){markers} {opt_type} {opt_desc}".strip()

    def _build_tree_lines(self, label: str, prefix: str = "", is_last: bool = True) -> list[str]:
        lines = []
        node = self.nodes.get(label)
        if not node:
            return lines
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + self._render_node(node))
        children = self._children.get(label, [])
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child_id in enumerate(sorted(children)):
            lines.extend(self._build_tree_lines(child_id, child_prefix, i == len(children) - 1))
        return lines
