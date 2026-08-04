# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the unified ``Evaluator`` entrypoint (dataset-driven + task-driven)."""

from collections.abc import Sequence
from typing import Any, cast

import pytest
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.execution.backends.local.backend import LocalBackend
from nemo_evaluator_sdk.execution.evaluator import Evaluator
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class _ConstantMetric:
    """Metric that scores every trial with a constant value (no inference needed)."""

    @property
    def type(self) -> str:
        return "constant_metric"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        return MetricResult(outputs=[MetricOutput(name="score", value=0.75)])


class _TaskRunner:
    """Serializable-free ``AgentTaskRunner`` that fabricates one trial per task."""

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        return [
            AgentEvalTrial(
                id=f"{task.id}:runtime",
                task_id=task.id,
                status=AgentEvalTrialStatus.COMPLETED,
                output=AgentOutput(output_text="Runtime answer"),
                metadata={"model_id": "runtime"},
            )
            for task in tasks
        ]


def _task() -> AgentEvalTask:
    return AgentEvalTask(
        id="task-1",
        intent="Answer the prompt.",
        inputs={"instruction": "What is the answer?"},
        metrics=[_ConstantMetric()],
    )


def _candidate_trial() -> AgentEvalTrial:
    return AgentEvalTrial(
        id="trial-1",
        task_id="task-1",
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(output_text="Candidate answer"),
        metadata={"model_id": "candidate"},
    )


def _sentinel_result() -> AgentEvalResult:
    return AgentEvalResult(
        run_id="sentinel",
        tasks=[],
        trials=[],
        scores=[],
        summary=AgentEvalSummary.from_scores([], tasks=[]),
        benchmark={},
    )


class _RecordingTaskBackend:
    """Async backend exposing only ``evaluate_taskset`` to prove the injection seam."""

    def __init__(self, result: AgentEvalResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def evaluate_dataset(self, *, metrics: Any, **kwargs: Any) -> Any:  # pragma: no cover - unused
        raise AssertionError("dataset path should not be exercised")

    async def evaluate_taskset(self, **kwargs: Any) -> AgentEvalResult:
        self.calls.append(kwargs)
        return self.result


class _RecordingSyncTaskBackend:
    """Sync backend twin, adapted to the async contract by ``Evaluator``."""

    def __init__(self, result: AgentEvalResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def evaluate_dataset(self, *, metrics: Any, **kwargs: Any) -> Any:  # pragma: no cover - unused
        raise AssertionError("dataset path should not be exercised")

    def evaluate_taskset(self, **kwargs: Any) -> AgentEvalResult:
        self.calls.append(kwargs)
        return self.result


def test_dataset_methods_mirror_backend_operations() -> None:
    # The Evaluator exposes one dataset method per backend dataset operation, plus the
    # backward-compatible ``run`` / ``run_sync`` dispatchers.
    for name in (
        "run_dataset_eval",
        "run_dataset_eval_sync",
        "run_taskset_eval",
        "run_taskset_eval_sync",
        "run",
        "run_sync",
    ):
        assert callable(getattr(Evaluator, name))


def test_run_dispatches_single_metric_to_metric_eval() -> None:
    # A single metric routes through the metric path and returns a single-metric result.
    result = Evaluator().run_sync(_ConstantMetric(), [{"reference": "x", "output_text": "x"}])
    assert type(result).__name__ == "EvaluationResult"


def test_run_dispatches_sequence_to_benchmark_eval() -> None:
    # A sequence routes through the benchmark path and returns a multi-metric result.
    result = Evaluator().run_sync([_ConstantMetric()], [{"reference": "x", "output_text": "x"}])
    assert type(result).__name__ == "BenchmarkEvaluationResult"


async def test_run_task_eval_scores_precomputed_trials() -> None:
    result = await Evaluator().run_taskset_eval(taskset=[_task()], trials=[_candidate_trial()])

    assert isinstance(result, AgentEvalResult)
    assert result.run_id
    assert len(result.scores) == 1
    assert result.scores[0].status == AgentEvalScoreStatus.COMPLETED


def test_run_task_eval_sync_scores_precomputed_trials() -> None:
    result = Evaluator().run_taskset_eval_sync(taskset=[_task()], trials=[_candidate_trial()])

    assert isinstance(result, AgentEvalResult)
    assert len(result.scores) == 1


async def test_run_task_eval_generates_trials_from_task_runner_target() -> None:
    result = await Evaluator().run_taskset_eval(
        taskset=[_task()],
        target=_TaskRunner(),
        config=AgentEvalRunConfig(write_dashboard=False),
    )

    assert [trial.id for trial in result.trials] == ["task-1:runtime"]
    assert result.scores[0].status == AgentEvalScoreStatus.COMPLETED


async def test_run_task_eval_rejects_trials_and_target_together() -> None:
    with pytest.raises(ValueError, match="exactly one of trials or target"):
        # cast past the mutually-exclusive overloads to exercise the runtime guard.
        await cast(Any, Evaluator()).run_taskset_eval(
            taskset=[_task()], trials=[_candidate_trial()], target=_TaskRunner()
        )


def test_local_backend_rejects_inference_and_factory() -> None:
    with pytest.raises(ValueError, match="either inference_fn or agent_inference_fn_factory"):
        LocalBackend(
            inference_fn=cast(Any, lambda *a, **k: None),
            agent_inference_fn_factory=cast(Any, lambda *a, **k: None),
        )


async def test_run_task_eval_delegates_to_injected_async_backend() -> None:
    sentinel = _sentinel_result()
    backend = _RecordingTaskBackend(sentinel)

    result = await Evaluator(backend).run_taskset_eval(taskset=[_task()], trials=[_candidate_trial()])

    assert result is sentinel
    assert len(backend.calls) == 1
    assert backend.calls[0]["target"] is None
    assert [task.id for task in backend.calls[0]["taskset"]] == ["task-1"]


async def test_run_task_eval_delegates_to_injected_sync_backend() -> None:
    sentinel = _sentinel_result()
    backend = _RecordingSyncTaskBackend(sentinel)

    result = await Evaluator(backend).run_taskset_eval(taskset=[_task()], trials=[_candidate_trial()])

    assert result is sentinel
    assert len(backend.calls) == 1
