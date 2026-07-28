# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist plugin entity definitions — stored in the NeMo Platform entity store."""

from typing import Any, Literal, Sequence

from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import TrialResult
from nemo_platform_plugin.entity import NemoEntity
from pydantic import ConfigDict, Field, model_validator


class ExperimentRun(NemoEntity, entity_type="experiment_run"):
    """Tracks a single Experimentalist optimization run end-to-end.

    Enables resumability and listing all runs for an insight. Created when a
    run starts, updated on each round, and finalized (with summary and
    winner) when the run completes or fails.
    """

    model_config = ConfigDict(validate_assignment=True)

    # --- immutable: set at creation, never updated ---
    agent: str = Field(frozen=True, description="Name or path of the agent under test.")
    insight: str | None = Field(
        frozen=True,
        default=None,
        description=(
            "Id of the Insight this run is optimizing against, or a local "
            "filesystem path to the insight fixture when running offline. "
            "None for Mode 2 (dataset-driven) runs."
        ),
    )
    config_snapshot: dict[str, Any] = Field(
        frozen=True,
        default_factory=dict,
        description="EvolutionaryOptimizerConfig fields at run creation time.",
    )
    # --- mutable: updated throughout the run lifecycle ---
    status: Literal["running", "completed", "failed"] = Field(
        default="running",
        description="Lifecycle status of this optimization run.",
    )
    rounds_completed: int = Field(
        default=0,
        description="Number of full optimization rounds completed so far.",
    )
    winner_agent: str | None = Field(
        default=None,
        description=(
            "Entity id of the winning Candidate, or a local filesystem path "
            "to the agent directory when running offline; set on completion."
        ),
    )
    summary: str | None = Field(
        default=None,
        description="Human-readable summary of the run; filled by persist_result.",
    )

    @model_validator(mode="wrap")
    @classmethod
    def _restore_id_from_json(cls, data: Any, handler: Any) -> "ExperimentRun":
        """Restore computed field ``id`` when deserializing from JSON.

        The ``id`` property is a computed field backed by private ``_id``. It serializes
        to JSON but ``model_validate`` ignores computed fields during deserialization,
        so the private ``_id`` must be restored from the serialized ``"id"`` key.
        Without this, resumed runs lose their identity and projection names collapse.
        """
        if isinstance(data, dict) and "id" in data:
            # Pydantic wraps the dict during validation, extract the raw data
            instance = handler(data)
            instance._id = data["id"]  # type: ignore[attr-defined]
            return instance
        return handler(data)


class Candidate(NemoEntity, entity_type="candidate"):
    """A candidate agent version produced during an Experimentalist run.

    Lives in the entity store so candidates are queryable, resumable, and
    survive the local working directory being deleted.  ``run_id`` groups all
    candidates for a single ExperimentRun.

    Like every entity in this plugin, a Candidate's durable identity is its
    store-assigned ``id`` (``name`` is left for the store to auto-slug).
    ``label`` is the run-scoped handle ("agent-0", "agent-1", ...) used for the
    working directory, evolution-tree key, and ``ancestor`` references; it is
    unique within a run, not globally.

    ``artifacts`` is a runtime-only dict (excluded from serialization) that
    the loop uses to attach transient objects (e.g. agent directory paths)
    without polluting the persisted record.
    """

    workspace: str = Field(
        default="default",
        description="NeMo Platform workspace this candidate belongs to.",
    )
    run_id: str = Field(
        ...,
        description="ExperimentRun entity id that this candidate belongs to.",
    )
    label: str = Field(
        ...,
        description=(
            "Run-scoped handle for this candidate (e.g. 'agent-0'): the working "
            "directory name, evolution-tree key, and target of ``ancestor`` "
            "references. Unique within a run, not globally — the store-assigned "
            "``id`` is the durable identity."
        ),
    )
    ancestor: str | None = Field(
        default=None,
        description="Parent Candidate ``label``. None means this is the baseline (round 0).",
    )
    round: int = Field(description="Optimization round that produced this candidate. 0 = baseline.")
    optimization: str = Field(
        description=(
            "Graph-level description of the architecture change that produced this candidate "
            "(nodes added/removed/modified, edges changed, prompts rewritten). "
            "No source file paths or line numbers."
        ),
    )
    optimization_type: str | None = Field(
        default=None,
        description="OptimizationType literal that categorizes the change.",
    )
    task_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Task ids the Proposer flagged as most exercising this candidate's root "
            "cause; the coder uses them to validate the fix during subproblem refinement."
        ),
    )
    train_reward: dict[str, float] | None = Field(
        default=None,
        description="Multi-dimensional reward on the training split.",
    )
    train_reward_details: Sequence[TrialResult] | None = Field(
        default=None,
        description="Train split trial results from the last evaluation run.",
    )
    validation_reward: dict[str, float] | None = Field(
        default=None,
        description="Multi-dimensional reward on the validation split.",
    )
    validation_reward_details: Sequence[TrialResult] | None = Field(
        default=None,
        description="Validation split trial results from the last evaluation run.",
    )
    insight_reward: dict[str, float] | None = Field(
        default=None,
        description="Multi-dimensional reward on the materialized Insight suite.",
    )
    insight_reward_details: Sequence[TrialResult] | None = Field(
        default=None,
        description="Insight-suite trial results from the last evaluation run.",
    )
    insight_suite_identity: str | None = Field(
        default=None,
        description="Content identity of the Insight suite associated with insight_reward.",
    )
    insight_metric_keys: list[str] | None = Field(
        default=None,
        description="Validated runtime metric keys associated with insight_reward.",
    )
    validation_trajectory_reward: dict[str, float] | None = Field(
        default=None,
        description="Validation trajectory reward: aggregate + per-node scores.",
    )
    validation_trajectory_reward_details: dict[str, Any] | None = Field(
        default=None,
        description="Validation trajectory reward details: node_id → task_id → {reward, explanation}.",
    )
    killed_round: int | None = Field(
        default=None,
        description="Round in which this candidate was eliminated. None means still alive.",
    )
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
        description="Runtime-only artifacts (not persisted to the entity store).",
    )

    def __repr__(self) -> str:
        parts = [f"Candidate(label={self.label!r}, round={self.round}"]
        if self.ancestor is not None:
            parts.append(f", ancestor={self.ancestor!r}")
        parts.append(f", optimization={self.optimization!r}")
        if self.optimization_type is not None:
            parts.append(f", optimization_type={self.optimization_type!r}")
        if self.train_reward:
            scores = ", ".join(f"{k}={v:.3f}" for k, v in self.train_reward.items())
            parts.append(f", train_reward={{{scores}}}")
        if self.validation_reward:
            scores = ", ".join(f"{k}={v:.3f}" for k, v in self.validation_reward.items())
            parts.append(f", validation_reward={{{scores}}}")
        if self.insight_reward:
            scores = ", ".join(f"{k}={v:.3f}" for k, v in self.insight_reward.items())
            parts.append(f", insight_reward={{{scores}}}")
        if self.killed_round is not None:
            parts.append(f", killed_round={self.killed_round}")
        parts.append(")")
        return "".join(parts)

    def slim(self) -> "Candidate":
        """Return a copy without per-trial detail fields (safe to pass to LLM methods)."""
        return self.model_copy(
            update={
                "train_reward_details": None,
                "validation_reward_details": None,
                "insight_reward_details": None,
                "validation_trajectory_reward_details": None,
            }
        )
