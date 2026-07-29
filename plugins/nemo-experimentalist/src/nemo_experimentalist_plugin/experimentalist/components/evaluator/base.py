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

EvaluatorType: TypeAlias = Literal["harbor"]


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

    def prepare_dataset(self, dataset: Dataset) -> Dataset:
        """Bind evaluator-specific runtime behavior to a dataset."""
        return dataset

    async def aggregate_results(self, results: Sequence[TrialResult]) -> dict[str, float | int]:
        """
        Aggregate evaluation results from multiple runs.

        Defaults to averaging each metric across all trials, treating trials that
        did not emit a metric (e.g. failed trials) as contributing 0. The denominator
        is always ``len(results)``, not the number of trials that reported each metric,
        so failure counts against the aggregate score.

        Args:
            results(Sequence[TrialResult]): List of trial results to aggregate.

        Returns:
            dict[str, float | int]: Aggregated metric values keyed by metric name.
        """
        if not results:
            return {}

        completed = [r for r in results if r.status != "failed"]
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
