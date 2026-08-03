# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The run-config tree for one Experimentalist run.

One home for the whole tree. Component-owned slices (``CoderConfig``, ``AnalyzerConfig``,
...) are imported from the components that consume them rather than redeclared here --
``resolve.py`` used to carry a second copy of each because importing a component module
required credentials, which it no longer does.
"""

import os
from pathlib import Path
from typing import Any

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.analyzer import AnalyzerConfig
from nemo_experimentalist_plugin.experimentalist.components.coder import CoderConfig
from nemo_experimentalist_plugin.experimentalist.components.goal_tree import GoalTreeConfig
from nemo_experimentalist_plugin.experimentalist.components.proposer import ProposerConfig
from pydantic import BaseModel, Field, model_validator


class AgentSourceConfig(BaseModel):
    """Git/source modifiers for an experiment."""

    clone_depth: int | None = None
    source_path: str | None = None
    entrypoint: str | None = None


class CandidateStorageConfig(BaseModel):
    """Candidate persistence settings."""

    archive_candidates: bool = False
    candidate_branch_prefix: str = "optimizer"
    publish_winner: bool = False
    pr_draft: bool = True
    pr_base_branch: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    pr_labels: list[str] = Field(default_factory=list)


class ModelsConfig(BaseModel):
    """Model name per tier, mirroring the ``models:`` key in the benchmark configs.

    Environment remains the mechanism -- :func:`apply_to_env` writes the configured names
    into ``EXPERIMENTALIST_*_MODEL_NAME`` before any agent is constructed, and an unset
    tier keeps whatever the environment already provides. Credentials stay environment-only
    and are never accepted here.
    """

    smart: str | None = Field(default=None, description="Model for the smart tier, as your endpoint names it.")
    mid: str | None = Field(default=None, description="Model for the mid tier, as your endpoint names it.")
    fast: str | None = Field(default=None, description="Model for the fast tier, as your endpoint names it.")

    def apply_to_env(self, env: dict[str, str] | None = None) -> list[str]:
        """Write the configured tiers into the environment; return the names written."""
        target = os.environ if env is None else env
        written: list[str] = []
        for tier in ("smart", "mid", "fast"):
            value = getattr(self, tier)
            if value:
                target[f"EXPERIMENTALIST_{tier.upper()}_MODEL_NAME"] = value
                written.append(tier)
        return written


class EvolutionaryOptimizerConfig(BaseModel):
    """Complete schema for one optimizer run."""

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_curator_config(cls, data: Any) -> Any:
        if isinstance(data, dict) and "curator" in data:
            raise ValueError("'curator' was renamed to 'eval_author'; update the optimizer configuration")
        return data

    max_rounds: int = Field(default=15, description="Hard ceiling on optimization rounds.")
    min_rounds_before_stopping: int = Field(
        default=3, description="Rounds that must complete before the convergence check may stop the run."
    )
    max_survivors: int = Field(default=3, description="Candidates carried into the next round as parents.")
    max_candidates: int = Field(default=3, description="Candidates proposed per round.")
    max_trajectory_tasks: int = Field(default=8, description="Tasks scored per round by the trajectory scorer.")
    max_train_batch_tasks: int | None = Field(
        default=None, description="Train tasks sampled per round; None evaluates the full split."
    )
    train_batch_seed: int = Field(default=0, description="Seed for the per-round train batch sample.")
    max_summary_tokens: int = Field(default=80_000, description="Token budget for context summarization.")
    model_catalog_path: Path | None = Field(
        default=None, description="Model catalog overriding the packaged assets/models.yaml."
    )
    disable_trajectory_scoring: bool = Field(
        default=False, description="Skip goal-tree trajectory scoring and the goal tree it needs."
    )
    disable_convergence_check: bool = Field(
        default=False, description="Stop only on max_rounds, never on the terminator's convergence judgement."
    )
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    source: AgentSourceConfig = Field(default_factory=AgentSourceConfig)
    storage: CandidateStorageConfig = Field(default_factory=CandidateStorageConfig)
    goal_config: GoalTreeConfig = Field(default_factory=GoalTreeConfig)
    coder: CoderConfig = Field(default_factory=CoderConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    proposer: ProposerConfig = Field(default_factory=ProposerConfig)
    evaluator: dict[str, Any] = Field(default_factory=dict)
    eval_author: EvalAuthorConfig = Field(default_factory=EvalAuthorConfig)
