# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core data models for the Experimentalist's optimization loop.

Ported from AAD ``skills/eval-and-optimize-base/scripts/optimizer/models.py``.
Pure data — no platform dependencies — shared vocabulary between the loop,
analyzer, proposer, coder, and evaluator.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal, TypeVar

from nemo_experimentalist_plugin.entities import Candidate
from pydantic import BaseModel, Field

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
    def generation(self) -> int:
        return self.candidate.generation

    @property
    def optimization_type(self) -> str | None:
        """The kind of change this candidate's Proposal asked for, when it had one."""
        origin = self.candidate.generated_from
        value = origin.payload.get("optimization_type") if origin is not None else None
        return value if isinstance(value, str) else None

    @property
    def description(self) -> str:
        return self.candidate.description

    @property
    def train_reward(self) -> dict[str, float]:
        return self.candidate.rewards["train"].metrics or {}

    @property
    def val_reward(self) -> dict[str, float]:
        return self.candidate.rewards["validation"].metrics or {}

    @property
    def trajectory_reward(self) -> dict[str, float]:
        return self.candidate.rewards["validation-trajectory"].metrics or {}

    @property
    def is_survivor(self) -> bool:
        return self.candidate.killed_generation is None

    @property
    def reward_str(self) -> str:
        """One-line reward summary over every measured channel, not a fixed three."""
        parts = [
            f"{channel}[{_format_reward(record.metrics)}]"
            for channel, record in sorted(self.candidate.rewards.items())
            if record.metrics
        ]
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
    def from_candidates(cls, candidates: Iterable[Candidate]) -> EvolutionTree:
        """Rebuild the full tree from the run's persisted candidates.

        The tree is a view over stored entities, not over a directory layout — which
        is what lets a strategy resume without checkpointing its population.
        """
        tree = cls()
        for candidate in candidates:
            tree.add(candidate)
        return tree

    def survivors(self, max_generation: int | None = None) -> list[Candidate]:
        """Return alive candidates up to *max_generation* (or all if None)."""
        return [
            n.candidate
            for n in self.nodes.values()
            if n.is_survivor and (max_generation is None or n.generation <= max_generation)
        ]

    def add(self, candidate: Candidate) -> EvolutionNode:
        """Add or update a candidate in the tree, keyed by its durable id."""
        key = candidate.id or candidate.label
        if key in self.nodes:
            node = self.nodes[key]
            node.candidate = candidate
            return node
        node = EvolutionNode(candidate=candidate)
        self.nodes[key] = node
        self._children.setdefault(candidate.ancestor or "__root__", []).append(key)
        return node

    def mark_best(self, key: str) -> None:
        """Designate the node under *key* as the best, clearing all other best flags.

        *key* is a candidate id, which is what :meth:`add` files nodes under. Raising on
        an unknown key is deliberate: a display label would otherwise no-op silently.

        Raises:
            KeyError: if no node is filed under *key*.
        """
        if key not in self.nodes:
            raise KeyError(f"No candidate {key!r} in the evolution tree; keys are candidate ids")
        for node in self.nodes.values():
            node.is_best = False
        self.nodes[key].is_best = True

    def get_best(self) -> list[EvolutionNode]:
        """Return the Pareto-optimal nodes by validation reward."""
        scored = [n for n in self.nodes.values() if n.val_reward]
        if not scored:
            return []
        return pareto_front(scored, lambda n: n.val_reward)

    def to_markdown_table(self) -> str:
        """Export as a markdown table, one column per (channel, dimension) measured.

        Columns come from the channels actually present across the nodes, so a new reward
        channel appears here with no change to this method.
        """
        dimensions: dict[str, list[str]] = {}
        for node in self.nodes.values():
            for channel, record in node.candidate.rewards.items():
                seen = set(dimensions.setdefault(channel, []))
                dimensions[channel].extend(sorted(set(record.metrics) - seen))
        channels = sorted(dimensions)
        for channel in channels:
            dimensions[channel].sort()

        fixed = ["gen", "agent", "ancestor", "type"]
        reward_cols = [(channel, dimension) for channel in channels for dimension in dimensions[channel]]
        # Channel names in full, per M0's channel-agnostic rendering; the last column
        # follows the field it prints, which is `description` now.
        all_cols = fixed + [f"{channel}:{dimension}" for channel, dimension in reward_cols] + ["description"]
        header = "| " + " | ".join(all_cols) + " |"
        sep = "| " + " | ".join("---" for _ in all_cols) + " |"
        lines = [header, sep]

        for key in sorted(self.nodes, key=lambda k: (self.nodes[k].generation, self.nodes[k].label)):
            n = self.nodes[key]
            reward_vals = []
            for channel, dimension in reward_cols:
                metrics = n.candidate.rewards[channel].metrics
                reward_vals.append(f"{metrics[dimension]:.2f}" if dimension in metrics else "-")
            opt = (n.description or "")[:50].replace("\n", " ")
            cells = [
                str(n.generation),
                n.label,
                self._ancestor_label(n) or "-",
                n.optimization_type or "-",
            ]
            cells += [*reward_vals, opt]
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

    def _ancestor_label(self, node: EvolutionNode) -> str | None:
        """The ancestor's display handle, since ``ancestor`` is an id."""
        if node.ancestor is None:
            return None
        parent = self.nodes.get(node.ancestor)
        return parent.label if parent is not None else node.ancestor

    def _render_node(self, node: EvolutionNode) -> str:
        opt_type = f"[{node.optimization_type}]" if node.optimization_type else ""
        opt_desc = (node.description or "")[:40].replace("\n", " ")
        if opt_desc and len(node.description) > 40:
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


class MetricTarget(BaseModel):
    """One evaluator-produced metric and the desired direction of change."""

    name: str = Field(min_length=1, description="Exact metric name emitted by the evaluator.")
    direction: Literal["maximize", "minimize"] = Field(
        description="Whether higher or lower values are better for this target."
    )


def pareto_objectives(metrics: dict[str, float], objective_function: list[MetricTarget]) -> dict[str, float]:
    """Project evaluator metrics onto the configured objectives for Pareto ranking.

    The generic Pareto utility maximizes every dimension. Minimized objective
    values are sign-inverted here; regression metrics are intentionally absent.
    """
    objectives: dict[str, float] = {}
    for target in objective_function:
        value = metrics.get(target.name)
        if value is None:
            return {}
        objectives[target.name] = float(value) if target.direction == "maximize" else -float(value)
    return objectives


def has_metric_dimensions(metrics: dict[str, float], targets: list[MetricTarget]) -> bool:
    """Return whether an evaluator result contains every required metric target."""
    return all(target.name in metrics for target in targets)
