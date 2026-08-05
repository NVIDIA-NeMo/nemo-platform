# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The run-config tree for one Experimentalist run.

:class:`EvolutionaryOptimizerConfig` holds *run* parameters -- what one experiment does.
There is one per invocation, named explicitly with ``--config``, and nothing overrides it:
a stale ``NEMO_EXPERIMENTALIST_MAX_ROUNDS`` silently truncating a run whose config file
says otherwise would be a bad failure, and it would make ``config_snapshot`` a dishonest
record of what ran. It is therefore a plain ``BaseModel`` with no environment binding.

The other half of the configuration -- which endpoint this install talks to and with which
models -- is a deployment setting, lives in ``settings.py`` as a :class:`NemoConfig` like
every other plugin's, and *does* let the environment win over the config file.

Component-owned slices (``CoderConfig``, ``AnalyzerConfig``, ...) are imported from the
components that consume them rather than redeclared here -- ``resolve.py`` used to carry a
second copy of each because importing a component module required credentials, which it no
longer does.
"""

from pathlib import Path
from typing import Any

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.analyzer import AnalyzerConfig
from nemo_experimentalist_plugin.experimentalist.components.coder import CoderConfig
from nemo_experimentalist_plugin.experimentalist.components.goal_tree import GoalTreeConfig
from nemo_experimentalist_plugin.experimentalist.components.proposer import ProposerConfig
from nemo_experimentalist_plugin.experimentalist.components.selector import SelectorConfig
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


class EvolutionaryOptimizerConfig(BaseModel):
    """Parameters for one optimizer run, read from ``--config`` and nothing else.

    Deliberately not a :class:`NemoConfig`: these values describe a single experiment, are
    named explicitly on the command line, and are recorded in ``config_snapshot`` as the
    account of what ran. Letting an ambient environment variable override them would make
    that account wrong. Endpoint and model settings live in
    :class:`~nemo_experimentalist_plugin.settings.ExperimentalistConfig`.
    """

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_curator_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "curator" in data:
            raise ValueError("'curator' was renamed to 'eval_author'; update the optimizer configuration")
        if "models" in data:
            raise ValueError(
                "'models' is no longer a run-config key; model tiers are deployment settings. "
                "Set them under the 'experimentalist:' config section or as "
                "NEMO_EXPERIMENTALIST_MODELS_{SMART,MID,FAST}."
            )
        return data

    strategy: str = Field(
        default="evolutionary",
        description=(
            "Registered 'strategy' component the runner runs. Ours is resolved by name "
            "like any other, so a strategy shipped by another package is selected here "
            "with no code change."
        ),
    )
    # Every step the strategy delegates to is named here, so swapping one is configuration.
    # A null means "no such step": turning a step off is the degenerate case of choosing a
    # different implementation, which is why there are no disable_* booleans.
    analyzer: str | None = Field(
        default="agent-trace",
        description="Registered 'root-cause-analyzer'. Null skips diagnosis and the train eval feeding it.",
    )
    proposer: str = Field(default="code-change", description="Registered 'proposer' emitting each round's Proposals.")
    terminator: str | None = Field(
        default="convergence",
        description="Registered 'terminator'. Null stops only on max_rounds.",
    )
    trajectory_scorer: str | None = Field(
        default="goal-tree",
        description="Registered 'trajectory-scorer'. Null skips step scoring and the goal tree it needs.",
    )
    selector: str = Field(
        default="pareto-llm-diversity",
        description="Registered 'selector' component choosing survivors and the winner.",
    )
    selector_config: SelectorConfig = Field(default_factory=SelectorConfig, description="Tuning for the selector.")
    builder: str = Field(
        default="coder",
        description=(
            "Registered 'builder' component that turns a Proposal into a Candidate. "
            "Swap it for one shipped by another package to change how candidates are "
            "built without touching the loop."
        ),
    )
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

    source: AgentSourceConfig = Field(default_factory=AgentSourceConfig)
    storage: CandidateStorageConfig = Field(default_factory=CandidateStorageConfig)
    goal_config: GoalTreeConfig = Field(default_factory=GoalTreeConfig)
    coder: CoderConfig = Field(default_factory=CoderConfig)
    analyzer_config: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    proposer_config: ProposerConfig = Field(default_factory=ProposerConfig)
    evaluator: dict[str, Any] = Field(default_factory=dict)
    eval_author: EvalAuthorConfig = Field(default_factory=EvalAuthorConfig)
