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
components that consume them rather than redeclared here -- ``resolve.py`` used to carry a
second copy of each because importing a component module required credentials, which it no
longer does.
"""

from pathlib import Path
from typing import Any, Literal, Self

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.analyzer import AnalyzerConfig
from nemo_experimentalist_plugin.experimentalist.components.coder import CoderConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorTypeField
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
    publish_winner: bool = True
    pr_draft: bool = True
    pr_base_branch: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    pr_labels: list[str] = Field(default_factory=list)


class MetricTarget(BaseModel):
    """One evaluator-produced metric and the desired direction of change."""

    name: str = Field(min_length=1, description="Exact metric name emitted by the evaluator.")
    direction: Literal["maximize", "minimize"] = Field(
        description="Whether higher or lower values are better for this target."
    )
    target: float | None = Field(
        default=None,
        description=(
            "Value at which this objective counts as satisfied, in the metric's own "
            "units. When every targeted objective is met the run stops, so a solved "
            "problem stops paying for rounds. Unset means no such stop: metrics are not "
            "required to be normalized, so there is no value that means 'as good as "
            "possible' for an arbitrary one."
        ),
    )

    def is_satisfied_by(self, value: float | None) -> bool:
        """Whether *value* meets this target. False when either side is absent.

        A missing measurement is not evidence of success, and a target that was never
        configured must not end a run.
        """
        if value is None or self.target is None:
            return False
        return value >= self.target if self.direction == "maximize" else value <= self.target


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


class EvolutionaryOptimizerConfig(BaseModel):
    """Parameters for one optimizer run, read from ``--config`` and nothing else.

    Deliberately not a :class:`NemoConfig`: these values describe a single experiment, are
    named explicitly on the command line, and are recorded in ``config_snapshot`` as the
    account of what ran. Letting an ambient environment variable override them would make
    that account wrong. Agent model settings live in the active Platform CLI context.
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
                "'models' is no longer a run-config key. Run `nemo setup` to select the default and fast agent models."
            )
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
    goal_config: GoalTreeConfig = Field(default_factory=GoalTreeConfig)
    coder: CoderConfig = Field(default_factory=CoderConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    proposer: ProposerConfig = Field(default_factory=ProposerConfig)
    evaluator_type: EvaluatorTypeField = "harbor_native"
    evaluator: dict[str, Any] = Field(default_factory=dict)
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
