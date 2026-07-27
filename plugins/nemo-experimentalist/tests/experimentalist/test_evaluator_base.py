# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import statistics
from pathlib import Path
from typing import Sequence

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    Evaluator,
    EvaluatorConfig,
    MetricResult,
    TrialResult,
)

_HAPPY_PATH_TRIAL_RESULTS = [
    TrialResult(
        id="trial1",
        task_id="task1",
        status="completed",
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.95),
            "loss": MetricResult(name="loss", value=0.05),
        },
    ),
    TrialResult(
        id="trial2",
        task_id="task1",
        status="completed",
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.90),
            "loss": MetricResult(name="loss", value=0.10),
        },
    ),
    TrialResult(
        id="trial3",
        task_id="task1",
        status="completed",
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.85),
            "loss": MetricResult(name="loss", value=0.15),
        },
    ),
]

_FAILED_TRIAL_RESULTS = [
    TrialResult(
        id="trial1",
        task_id="task1",
        status="completed",
        metrics={
            "loss": MetricResult(name="loss", value=0.05),
            "accuracy": MetricResult(name="accuracy", value=0.95),
        },
    ),
    TrialResult(
        id="trial1",
        task_id="task1",
        status="failed",
        metrics={},
    ),
]
_MISSING_METRIC_TRIAL_RESULTS = [
    TrialResult(
        id="trial1",
        task_id="task1",
        status="completed",
        metrics={
            "loss": MetricResult(name="loss", value=0.05),
            "accuracy": MetricResult(name="accuracy", value=0.95),
        },
    ),
    TrialResult(
        id="trial2",
        task_id="task1",
        status="completed",
        metrics={
            "accuracy": MetricResult(name="accuracy", value=0.90),
        },
    ),
]


class ConcreteEvaluator(Evaluator):
    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        return [
            TrialResult(
                id="trial",
                task_id="task",
                status="completed",
                metrics={"reward": MetricResult(name="reward", value=1.0)},
            )
        ]


class CustomAggregatorEvaluator(Evaluator):
    async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
        return []

    async def aggregate_results(self, results: Sequence[TrialResult]) -> dict[str, float | int]:
        metric_names = results[0].metrics.keys() if results else []
        aggregated_metrics = {}
        for metric_name in metric_names:
            values = [result.metrics[metric_name].value for result in results]
            aggregated_metrics[metric_name] = statistics.median(values)
        return aggregated_metrics


def test_cannot_instantiate_abstract_evaluator():
    with pytest.raises(TypeError):
        Evaluator(options=EvaluatorConfig())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trial_results,expected_aggregated_metrics,expected_error",
    [
        (
            _HAPPY_PATH_TRIAL_RESULTS,
            {
                "accuracy": (0.95 + 0.90 + 0.85) / 3,
                "loss": (0.05 + 0.10 + 0.15) / 3,
            },
            None,
        ),
        (
            _FAILED_TRIAL_RESULTS,
            {
                "loss": 0.05,
                "accuracy": 0.95,
            },
            None,
        ),
        (
            _MISSING_METRIC_TRIAL_RESULTS,
            None,
            ValueError,
        ),
    ],
)
async def test_default_aggregation(trial_results, expected_aggregated_metrics, expected_error):
    evaluator = ConcreteEvaluator(options=EvaluatorConfig())
    if expected_error:
        with pytest.raises(expected_error):
            await evaluator.aggregate_results(trial_results)
    else:
        aggregated_metrics = await evaluator.aggregate_results(trial_results)
        assert aggregated_metrics == expected_aggregated_metrics


@pytest.mark.asyncio
async def test_custom_aggregator():
    trial_results = _HAPPY_PATH_TRIAL_RESULTS
    evaluator = CustomAggregatorEvaluator(options=EvaluatorConfig())
    aggregated_metrics = await evaluator.aggregate_results(trial_results)
    assert aggregated_metrics == {
        "accuracy": 0.90,
        "loss": 0.10,
    }


@pytest.mark.asyncio
async def test_aggregate_results_empty():
    evaluator = ConcreteEvaluator(options=EvaluatorConfig())
    result = await evaluator.aggregate_results([])
    assert result == {}


@pytest.mark.asyncio
async def test_aggregate_results_all_failed():
    evaluator = ConcreteEvaluator(options=EvaluatorConfig())
    failed_trials = [
        TrialResult(id="t1", task_id="task1", status="failed", metrics={}),
        TrialResult(id="t2", task_id="task1", status="failed", metrics={}),
    ]
    result = await evaluator.aggregate_results(failed_trials)
    assert result == {}


@pytest.mark.asyncio
async def test_run_returns_result_when_all_trials_failed():
    class AllFailedEvaluator(ConcreteEvaluator):
        async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
            return [
                TrialResult(id="t1", task_id="task1", status="failed", metrics={}),
                TrialResult(id="t2", task_id="task2", status="failed", metrics={}),
            ]

    evaluator = AllFailedEvaluator(options=EvaluatorConfig())
    result = await evaluator.run(agent=Path("/tmp/agent"), dataset=Dataset(id="ds"))
    assert result.aggregate_metrics == {}
    assert len(result.trials) == 2


@pytest.mark.asyncio
async def test_run_accepts_explicit_zero_metric():
    class ZeroRewardEvaluator(ConcreteEvaluator):
        async def _run(self, agent: Path, dataset: Dataset, options: EvaluatorConfig) -> Sequence[TrialResult]:
            return [
                TrialResult(
                    id="t1",
                    task_id="task1",
                    status="completed",
                    metrics={"reward": MetricResult(name="reward", value=0.0)},
                )
            ]

    evaluator = ZeroRewardEvaluator(options=EvaluatorConfig())
    result = await evaluator.run(agent=Path("/tmp/agent"), dataset=Dataset(id="ds"))
    assert result.aggregate_metrics == {"reward": 0.0}


@pytest.mark.asyncio
async def test_run_with_none_options_uses_default():
    class ConcreteDataset(Dataset):
        @classmethod
        def from_ref(cls, ref):
            return cls(id="test")

    evaluator = ConcreteEvaluator(options=EvaluatorConfig())
    dataset = ConcreteDataset(id="ds")
    result = await evaluator.run(agent=Path("/tmp/agent"), dataset=dataset, options=None)
    assert result.id == "agent-ds"


@pytest.mark.asyncio
async def test_run_with_dict_options_merges():
    class ConcreteDataset(Dataset):
        @classmethod
        def from_ref(cls, ref):
            return cls(id="test")

    evaluator = ConcreteEvaluator(options=EvaluatorConfig(force_rerun=False))
    dataset = ConcreteDataset(id="ds")
    result = await evaluator.run(
        agent=Path("/tmp/agent"),
        dataset=dataset,
        options={"force_rerun": True},
    )
    assert result.id == "agent-ds"
