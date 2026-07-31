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

    smart: str | None = None
    mid: str | None = None
    fast: str | None = None

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

    max_rounds: int = 15
    min_rounds_before_stopping: int = 3
    max_survivors: int = 3
    max_candidates: int = 3
    max_trajectory_tasks: int = 8
    max_train_batch_tasks: int | None = None
    train_batch_seed: int = 0
    max_summary_tokens: int = 80_000
    model_catalog_path: Path | None = None
    disable_trajectory_scoring: bool = False
    disable_convergence_check: bool = False
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    source: AgentSourceConfig = Field(default_factory=AgentSourceConfig)
    storage: CandidateStorageConfig = Field(default_factory=CandidateStorageConfig)
    goal_config: GoalTreeConfig = Field(default_factory=GoalTreeConfig)
    coder: CoderConfig = Field(default_factory=CoderConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    proposer: ProposerConfig = Field(default_factory=ProposerConfig)
    evaluator: dict[str, Any] = Field(default_factory=dict)
    eval_author: EvalAuthorConfig = Field(default_factory=EvalAuthorConfig)
