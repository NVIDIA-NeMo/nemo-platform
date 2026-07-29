# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluator interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, TypeAlias

from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    Dataset,
    EvaluationResult,
    TrialResult,
)
from pydantic import BaseModel, ConfigDict, Field

EvaluatorType: TypeAlias = Literal["harbor", "harbor_agent_task_runner"]
"""Selects which evaluator drives the run.

``harbor_agent_task_runner`` is the default: orchestration belongs to the NeMo
Evaluator SDK's ``HarborAgentTaskRunner``, which owns the ``JobConfig``, the
success-aware job-dir cache, and agent import scoping. ``harbor`` builds and runs
Harbor's ``Job`` directly — the original behaviour, kept for comparison and as a
fallback when the SDK is unavailable.

Harbor runs the trials either way; only orchestration ownership differs. Both read
results back off the same job directory, so the trials the loop sees are equivalent.
"""


class EvaluatorConfig(BaseModel):
    """Configuration for evaluator run."""

    model_config = ConfigDict(extra="allow")
    force_rerun: bool = Field(
        default=False,
        description="Force the evaluator to run even if there is already a result for this agent and dataset.",
    )


class Evaluator(ABC):
    """Abstract base class for concrete evaluators."""

    evaluator_type: EvaluatorType

    def __init__(self, options: EvaluatorConfig, experiment_dir: Path | None = None) -> None:
        self.options = options
        self.experiment_dir = experiment_dir

    async def aggregate_results(self, results: Sequence[TrialResult]) -> dict[str, float | int]:
        """
        Aggregate evaluation results from multiple runs.

        Averages each metric over trials with ``status == "completed"``. Anything
        else is excluded from both the sum and the denominator, so a crash does not
        pull the mean down — it shrinks the sample the mean is taken over, and a
        round with no completed trial aggregates to ``{}`` rather than to zeros.

        Completed trials must all report the same metric keys; a mismatch raises
        rather than silently averaging over different denominators per metric.

        Args:
            results(Sequence[TrialResult]): List of trial results to aggregate.

        Returns:
            dict[str, float | int]: Aggregated metric values keyed by metric name.
        """
        if not results:
            return {}

        # Positive predicate on purpose: `!= "failed"` is equivalent while TrialStatus
        # is Literal["completed", "failed"], but it would silently start averaging any
        # third status someone adds. Opt statuses in, do not opt "failed" out.
        completed = [r for r in results if r.status == "completed"]
        if not completed:
            return {}

        expected_metrics = set(completed[0].metrics.keys())
        for result in completed[1:]:
            if set(result.metrics.keys()) != expected_metrics:
                missing = expected_metrics - set(result.metrics.keys())
                extra = set(result.metrics.keys()) - expected_metrics
                raise ValueError(f"Inconsistent metrics across trials. Missing: {missing}, extra: {extra}")

        aggregate_metrics: dict[str, float | int] = {}
        for result in completed:
            for metric_name, metric_result in result.metrics.items():
                if metric_name not in aggregate_metrics:
                    aggregate_metrics[metric_name] = metric_result.value
                else:
                    aggregate_metrics[metric_name] += metric_result.value

        for metric_name in aggregate_metrics:
            aggregate_metrics[metric_name] = aggregate_metrics[metric_name] / len(completed)
        return aggregate_metrics

    async def run(
        self,
        agent: Path,
        dataset: Dataset,
        options: EvaluatorConfig | dict | None = None,
    ) -> EvaluationResult:
        """
        Run an evaluation and return a domain result.

        Args:
            agent(Path): Path to the agent directory.
            dataset(Dataset): Dataset to evaluate.
            options(EvaluatorConfig | dict | None): Additional options to pass to the evaluator.
                Overrides the evaluator's default options. Dicts are coerced via
                model_validate against the evaluator's default options type.

        Returns:
            EvaluationResult: Evaluation result.
        """
        if options is None:
            options = self.options
        elif isinstance(options, dict):
            options = type(self.options).model_validate({**self.options.model_dump(), **options})
        trials = await self._run(agent, dataset, options)
        aggregate_metrics = await self.aggregate_results(trials)
        return EvaluationResult(
            id=f"{agent.name}-{dataset.id}",
            trials=trials,
            aggregate_metrics=aggregate_metrics,
            metadata={},
        )

    @abstractmethod
    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        """Run the evaluator and return a list of trial results.

        Args:
            agent(Path): Path to the agent directory.
            dataset(Dataset): Dataset to evaluate.
            options(EvaluatorConfig): Options to pass to the evaluator.

        Returns:
            Sequence[TrialResult]: List of trial results.

        Raises:
            ValueError: If the agent or dataset is not provided.
        """
        ...
