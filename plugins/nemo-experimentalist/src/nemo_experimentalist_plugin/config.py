# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The run-config tree for one Experimentalist run.

:class:`EvolutionaryOptimizerConfig` holds *run* parameters -- what one experiment does.
There is one per invocation, named explicitly with ``--config``, and nothing overrides it:
a stale ``NEMO_EXPERIMENTALIST_MAX_ROUNDS`` silently truncating a run whose config file
says otherwise would be a bad failure, and it would make ``config_snapshot`` a dishonest
record of what ran. It is therefore a plain ``BaseModel`` with no environment binding.

The optimizer's own default/fast model pair is selected by ``nemo setup`` and
stored in the active Platform CLI context.

Component-owned slices (``CoderConfig``, ``AnalyzerConfig``, ...) are imported from the
components that consume them rather than redeclared here.
"""

from pathlib import Path
from typing import Any, Self

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.analyzer import AnalyzerConfig
from nemo_experimentalist_plugin.experimentalist.components.coder import CoderConfig
from nemo_experimentalist_plugin.experimentalist.components.goal_tree import GoalTreeConfig
from nemo_experimentalist_plugin.experimentalist.components.models import (  # noqa: F401 - re-exported
    MetricTarget,
    has_metric_dimensions,
    pareto_objectives,
)
from nemo_experimentalist_plugin.experimentalist.components.proposer import ProposerConfig
from nemo_experimentalist_plugin.experimentalist.components.selector import SelectorConfig
from nemo_experimentalist_plugin.experimentalist.components.terminator import TerminatorConfig
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
    publish_winner: bool = True
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
    that account wrong. Agent model settings live in the active Platform CLI context.

    Unknown keys are tolerated, so a key that was *removed* has to be rejected explicitly
    below — silently ignoring one would change what the run does.
    """

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_curator_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "curator" in data:
            raise ValueError("'curator' was renamed to 'eval_author'; update the optimizer configuration")

        # A step is turned off by choosing no implementation of its role.
        for removed, replacement in (
            ("disable_convergence_check", "terminator"),
            ("disable_trajectory_scoring", "trajectory_scorer"),
        ):
            if removed in data:
                raise ValueError(
                    f"{removed!r} is no longer a run-config key; write '{replacement}: null' instead. "
                    "Turning a step off is how you choose no implementation of its role."
                )

        # The role key now names a component, so its tuning moved under '<role>_config'.
        # A string is a component name and stays valid; only a config block is legacy.
        for removed, replacement in (("analyzer", "analyzer_config"), ("proposer", "proposer_config")):
            if isinstance(data.get(removed), dict):
                raise ValueError(
                    f"{removed!r} now names the component to run, so its settings moved to {replacement!r}."
                )

        # Renamed outright. These are not fields at all, so any value here is legacy and
        # would otherwise be dropped in silence — changing what the run does.
        for removed, role, config_key in (
            ("evaluator", "outcome_evaluator", "outcome_evaluator_config"),
            # 'evaluation' said what the step produces; the role is the thing that does it,
            # and 'outcome' is what distinguishes it from the trajectory-scorer, which
            # measures the process of the same run.
            ("evaluation", "outcome_evaluator", "outcome_evaluator_config"),
            ("evaluation_config", "outcome_evaluator", "outcome_evaluator_config"),
            ("coder", "builder", "builder_config"),
            ("goal_config", "trajectory_scorer", "trajectory_scorer_config"),
        ):
            if removed in data:
                raise ValueError(
                    f"{removed!r} is no longer a run-config key; the role is {role!r} and its settings "
                    f"belong under {config_key!r}."
                )
        if "models" in data:
            raise ValueError(
                "'models' is no longer a run-config key. Run `nemo setup` to select the default and fast agent models."
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
    outcome_evaluator: str = Field(
        default="harbor",
        description=(
            "Registered 'outcome-evaluator' measuring what a candidate achieved. Named for "
            "the outcome because the trajectory-scorer measures the process of the same run."
        ),
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
    terminator_config: TerminatorConfig = Field(
        default_factory=TerminatorConfig, description="Tuning for the terminator."
    )
    builder: str = Field(
        default="llm-code-edit",
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

    objective_function: list[MetricTarget] = Field(
        default_factory=lambda: [MetricTarget(name="reward", direction="maximize")],
        min_length=1,
        description="Ordered evaluator metric targets this run should improve.",
    )
    regression_metrics: list[MetricTarget] = Field(
        default_factory=list,
        description="Metric target(s) that must not regress while the objective improves.",
    )
    source: AgentSourceConfig = Field(default_factory=AgentSourceConfig)
    storage: CandidateStorageConfig = Field(default_factory=CandidateStorageConfig)
    trajectory_scorer_config: GoalTreeConfig = Field(
        default_factory=GoalTreeConfig, description="Tuning for the trajectory scorer."
    )
    builder_config: CoderConfig = Field(default_factory=CoderConfig, description="Tuning for the builder.")
    analyzer_config: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    proposer_config: ProposerConfig = Field(default_factory=ProposerConfig)
    outcome_evaluator_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Config for the selected 'evaluation' component; its own model validates it.",
    )
    eval_author: EvalAuthorConfig = Field(default_factory=EvalAuthorConfig)

    @model_validator(mode="after")
    def validate_metric_contract(self) -> Self:
        objective_names = [target.name for target in self.objective_function]
        if len(objective_names) != len(set(objective_names)):
            raise ValueError("objective_function target names must be unique")
        regression_names = [target.name for target in self.regression_metrics]
        if len(regression_names) != len(set(regression_names)):
            raise ValueError("regression_metrics target names must be unique")
        overlap = set(objective_names).intersection(regression_names)
        if overlap:
            raise ValueError(
                "A metric cannot be both an objective and a regression target: " + ", ".join(sorted(overlap))
            )
        return self

    def optimization_policy(self) -> str:
        """Render the declared metric contract for optimizer-facing reasoning prompts."""

        def render(target: MetricTarget) -> str:
            return f"{target.name} ({target.direction})"

        objectives = ", ".join(render(target) for target in self.objective_function)
        regressions = ", ".join(render(target) for target in self.regression_metrics) or "none"
        return (
            f"Optimize these objective metric(s): {objectives}. "
            f"Do not regress these metric(s): {regressions}. "
            "Metric values, including aggregates, are produced by the evaluator; do not invent formulas or weights."
        )
