# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import builtins
import importlib
import inspect
import sys
from collections.abc import Callable, Sequence
from typing import Any, cast

import pytest
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.execution.backends.local.backend import LocalBackend
from nemo_evaluator_sdk.execution.config import RunConfig, RunConfigOnlineModel
from nemo_evaluator_sdk.execution.evaluator import Evaluator
from nemo_evaluator_sdk.execution.jobs import EvaluationJob, LocalJob, SyncEvaluationJob
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import FieldMapping, Model
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import AggregatedMetricResult
from pydantic import ValidationError
from pytest_mock import MockerFixture


class _CustomMetric:
    @property
    def type(self) -> str:
        return MetricType.STRING_CHECK.value

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        score = 1.0 if input.row.data["expected"] == input.row.data["model_output"] else 0.0
        return MetricResult(outputs=[MetricOutput(name="string-check", value=score)])

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("string-check")]


class _CandidateOutputMetric:
    @property
    def type(self) -> str:
        return "candidate-output-check"

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        score = 1.0 if input.candidate.output_text == input.row.data["reference"] else 0.0
        return MetricResult(outputs=[MetricOutput(name="match", value=score)])

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("match")]


_DATASET = [
    {"expected": "blue", "model_output": "Blue"},
    {"expected": "Jupiter", "model_output": "Saturn"},
]

_MAPPED_DATASET = [
    {"expected": "blue", "prediction": "blue"},
    {"expected": "Jupiter", "prediction": "Saturn"},
]


def _agent_task() -> AgentEvalTask:
    return AgentEvalTask(id="t", intent="i", inputs={"instruction": "do it"}, metrics=[])


async def _completed(value: Any) -> Any:
    """Return an already-known value from inside a task."""
    return value


async def _completed_taskset_run() -> AgentEvalResult:
    return _TASKSET_RESULT


_TASKS = [AgentEvalTask(id="t", intent="i", inputs={"instruction": "do it"}, metrics=[])]

_TARGET = Model(url="http://model.test/v1", name="m")

_TASKSET_RESULT = AgentEvalResult(run_id="r", tasks=[], trials=[], scores=[], summary=AgentEvalSummary())


class _CompletedSyncJob:
    """A sync already-finished job, the sync counterpart of ``LocalJob``.

    The SDK ships only the async ``LocalJob`` because ``LocalBackend`` is async; a third-party
    sync backend would need this shape.
    """

    def __init__(self, result: Any) -> None:
        self._result = result
        self.waits: list[dict[str, float]] = []

    def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = 10.0,
        job_timeout_seconds: float = 3600.0,
        pending_timeout_seconds: float = 600.0,
    ) -> None:
        self.waits.append(
            {
                "poll_interval_seconds": poll_interval_seconds,
                "job_timeout_seconds": job_timeout_seconds,
                "pending_timeout_seconds": pending_timeout_seconds,
            }
        )

    def get_result(self) -> Any:
        return self._result


def _empty_benchmark_result() -> BenchmarkEvaluationResult:
    return BenchmarkEvaluationResult(
        row_scores=[],
        aggregate_scores=AggregatedMetricResult(scores=[]),
        per_metric={},
    )


class _FakeDirectBackend:
    """Test backend that satisfies the evaluator protocol."""

    def __init__(self, result: BenchmarkEvaluationResult):
        self.result = result
        self.dataset_calls: list[dict[str, Any]] = []
        self.taskset_calls: list[dict[str, Any]] = []

    async def evaluate_dataset(
        self, *, metrics: Sequence[Metric], **kwargs: Any
    ) -> EvaluationJob[BenchmarkEvaluationResult]:
        self.dataset_calls.append({"metrics": metrics, **kwargs})
        return LocalJob(asyncio.create_task(_completed(self.result)))

    async def evaluate(self, **kwargs: Any) -> EvaluationJob[AgentEvalResult]:
        """Return an already-finished taskset job."""
        self.taskset_calls.append(kwargs)
        return LocalJob(asyncio.create_task(_completed_taskset_run()))


class _FakeSyncBackend:
    """Test backend that satisfies the sync evaluator protocol."""

    def __init__(self, result: BenchmarkEvaluationResult):
        self.result = result
        self.dataset_calls: list[dict[str, Any]] = []
        self.taskset_calls: list[dict[str, Any]] = []

    def evaluate_dataset(
        self, *, metrics: Sequence[Metric], **kwargs: Any
    ) -> SyncEvaluationJob[BenchmarkEvaluationResult]:
        self.dataset_calls.append({"metrics": metrics, **kwargs})
        return _CompletedSyncJob(self.result)

    def evaluate(self, **kwargs: Any) -> SyncEvaluationJob[AgentEvalResult]:
        """Return an already-finished taskset job."""
        self.taskset_calls.append(kwargs)
        return _CompletedSyncJob(_TASKSET_RESULT)


class _LoopSensitiveSyncBackend(_FakeSyncBackend):
    """Sync backend that fails if called on a thread with an active event loop."""

    def _raise_if_running_on_active_loop(self) -> None:
        """Raise when the sync backend is executing on an active event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("sync backend ran on an active event loop")

    def evaluate_dataset(
        self, *, metrics: Sequence[Metric], **kwargs: Any
    ) -> SyncEvaluationJob[BenchmarkEvaluationResult]:
        self._raise_if_running_on_active_loop()
        return super().evaluate_dataset(metrics=metrics, **kwargs)

    def evaluate(self, **kwargs: Any) -> SyncEvaluationJob[AgentEvalResult]:
        self._raise_if_running_on_active_loop()
        return super().evaluate(**kwargs)


class _MissingEvaluateBackend:
    """Invalid backend implementing only half the contract: dataset evaluation, no taskset."""

    async def evaluate_dataset(
        self, *, metrics: Sequence[Metric], **kwargs: Any
    ) -> EvaluationJob[BenchmarkEvaluationResult]:
        """Return an already-finished dataset job."""
        del metrics, kwargs
        return LocalJob(asyncio.create_task(_completed(_empty_benchmark_result())))


class _MixedBackend:
    """Invalid backend mixing async and sync contract methods.

    Complete — it implements both methods — so it reaches the async/sync discrimination rather than
    failing the presence check.
    """

    async def evaluate(self, **kwargs: Any) -> EvaluationJob[AgentEvalResult]:
        """Return an already-finished taskset job asynchronously."""
        del kwargs
        return LocalJob(asyncio.create_task(_completed_taskset_run()))

    def evaluate_dataset(
        self, *, metrics: Sequence[Metric], **kwargs: Any
    ) -> SyncEvaluationJob[BenchmarkEvaluationResult]:
        """Return an already-finished dataset job synchronously — the mismatch under test."""
        del metrics, kwargs
        return _CompletedSyncJob(_empty_benchmark_result())


class TestEvaluator:
    @pytest.mark.parametrize("flag_name", ["soft_fail", "fail_fast"])
    def test_run_config_rejects_run_level_failure_flags(self, flag_name: str) -> None:
        with pytest.raises(ValidationError):
            RunConfig.model_validate({"parallelism": 1, flag_name: True})

    def test_run_config_rejects_aggregate_fields(self) -> None:
        with pytest.raises(ValidationError):
            RunConfig.model_validate({"aggregate_fields": ["mean"]})

    def test_rejects_legacy_backend_argument(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())

        legacy_kwargs: dict = {"backend": backend}
        with pytest.raises(TypeError, match="backend"):
            Evaluator(**legacy_kwargs)

    @pytest.mark.asyncio
    async def test_run_uses_offline_params_without_request_fail_fast(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())
        evaluator = Evaluator(client=backend)

        await evaluator.run_dataset(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
            config=RunConfig(parallelism=1),
        )

        call = backend.dataset_calls[0]
        assert call["params"] == RunConfig(parallelism=1)
        # Local-only arguments are omitted when unset rather than forwarded as None, so a backend
        # that does not accept them is never handed them.
        assert "aggregate_fields" not in call
        assert "fail_fast" not in call

    @pytest.mark.asyncio
    async def test_run_preserves_aggregate_fields_on_request(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())
        evaluator = Evaluator(client=backend)

        await evaluator.run_dataset(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
            config=RunConfig(parallelism=1),
            aggregate_fields=("mean",),
        )

        call = backend.dataset_calls[0]
        assert call["params"] == RunConfig(parallelism=1)
        assert call["aggregate_fields"] == ("mean",)

    @pytest.mark.asyncio
    async def test_run_preserves_field_mapping_on_request(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())
        evaluator = Evaluator(client=backend)
        field_mapping = FieldMapping(output="prediction", reference="expected")

        await evaluator.run_dataset(
            metrics=[_CustomMetric()],
            dataset=_MAPPED_DATASET,
            field_mapping=field_mapping,
        )

        call = backend.dataset_calls[0]
        assert call["field_mapping"] == field_mapping

    @pytest.mark.asyncio
    async def test_run_preserves_ignored_online_request_failure_params(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())
        evaluator = Evaluator(client=backend)
        params = RunConfigOnlineModel(parallelism=1, ignore_request_failure=True)

        await evaluator.run_dataset(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
            config=params,
            target=Model(url="http://model.test/v1", name="test-model"),
        )

        call = backend.dataset_calls[0]
        assert call["params"] is params
        assert "fail_fast" not in call

    @pytest.mark.asyncio
    async def test_run_accepts_sdk_metric_instance(self):
        evaluator = Evaluator()

        result = await evaluator.run_dataset(
            metrics=[ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")],
            dataset=_DATASET,
            config=RunConfig(parallelism=2),
        )

        assert len(result.row_scores) == 2
        assert result.aggregate_scores.scores[0].name == "exact-match.exact-match"
        assert result.aggregate_scores.scores[0].mean == 0.5

    @pytest.mark.asyncio
    async def test_run_filters_aggregate_fields(self):
        evaluator = Evaluator()

        result = await evaluator.run_dataset(
            metrics=[ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")],
            dataset=_DATASET,
            config=RunConfig(parallelism=2),
            aggregate_fields=("mean",),
        )

        assert result.aggregate_scores.model_dump(mode="json") == {
            "scores": [{"name": "exact-match.exact-match", "count": 2, "mean": 0.5}]
        }

    @pytest.mark.asyncio
    async def test_run_accepts_mixed_sdk_and_custom_metrics(self):
        evaluator = Evaluator()

        result = await evaluator.run_dataset(
            metrics=[
                ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
                _CustomMetric(),
            ],
            dataset=_DATASET,
            config=RunConfig(parallelism=2),
        )

        assert list(result.per_metric) == ["exact-match", "string-check"]
        assert result.metric_result("exact-match").aggregate_scores.scores[0].name == "exact-match.exact-match"
        assert result.metric_result("string-check").aggregate_scores.scores[0].name == "string-check.string-check"

    @pytest.mark.asyncio
    async def test_run_filters_benchmark_aggregate_fields(self):
        evaluator = Evaluator()

        result = await evaluator.run_dataset(
            metrics=[
                ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
                _CustomMetric(),
            ],
            dataset=_DATASET,
            config=RunConfig(parallelism=2),
            aggregate_fields=("mean",),
        )

        assert result.aggregate_scores.model_dump(mode="json") == {
            "scores": [
                {"name": "exact-match.exact-match", "count": 2, "mean": 0.5},
                {"name": "string-check.string-check", "count": 2, "mean": 0.0},
            ]
        }
        assert result.metric_result("exact-match").aggregate_scores.model_dump(mode="json") == {
            "scores": [{"name": "exact-match.exact-match", "count": 2, "mean": 0.5}]
        }

    @pytest.mark.asyncio
    async def test_run_sync_matches_async_run(self):
        evaluator = Evaluator()
        metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")

        async_result = await evaluator.run_dataset(metrics=[metric], dataset=_DATASET, config=RunConfig(parallelism=2))
        sync_result = evaluator.run_dataset_sync(metrics=[metric], dataset=_DATASET, config=RunConfig(parallelism=2))

        assert async_result.model_dump(mode="python") == sync_result.model_dump(mode="python")
        assert isinstance(sync_result, BenchmarkEvaluationResult)

    def test_run_sync_custom_metric(self):
        evaluator = Evaluator()

        result = evaluator.run_dataset_sync(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
        )

        assert isinstance(result, BenchmarkEvaluationResult)
        assert result.aggregate_scores.scores[0].name == "string-check.string-check"
        assert result.row_scores[0].metrics["string-check"][0].value == 0.0
        assert result.row_scores[1].metrics["string-check"][0].value == 0.0

    def test_run_sync_field_mapping_populates_offline_candidate_output(self):
        evaluator = Evaluator()

        result = evaluator.run_dataset_sync(
            metrics=[_CandidateOutputMetric()],
            dataset=_MAPPED_DATASET,
            field_mapping=FieldMapping(output="prediction", reference="expected"),
        )

        assert result.aggregate_scores.scores[0].mean == 0.5
        assert result.row_scores[0].item["output"] == "blue"
        assert result.row_scores[0].sample["output_text"] == "blue"
        assert result.row_scores[0].metrics["candidate-output-check"][0].value == 1.0

    def test_run_sync_field_mapping_populates_benchmark_offline_candidate_output(self):
        evaluator = Evaluator()

        result = evaluator.run_dataset_sync(
            metrics=[ExactMatchMetric(reference="{{reference}}")],
            dataset=_MAPPED_DATASET,
            field_mapping=FieldMapping(output="prediction", reference="expected"),
        )

        assert result.aggregate_scores.scores[0].mean == 0.5
        assert result.row_scores[0].sample["output_text"] == "blue"

    @pytest.mark.asyncio
    async def test_run_uses_sync_backend_adapter_thread_bridge(self, mocker: MockerFixture):
        expected = _empty_benchmark_result()
        backend = _FakeSyncBackend(result=expected)
        evaluator = Evaluator(client=backend)

        async def run_in_thread(func: object, *args: object, **kwargs: object) -> object:
            """Execute the submitted sync callable while recording the thread boundary."""
            return cast(Callable[..., object], func)(*args, **kwargs)

        to_thread = mocker.patch(
            "nemo_evaluator_sdk.execution.evaluator.asyncio.to_thread",
            new=mocker.AsyncMock(side_effect=run_in_thread),
        )

        result = await evaluator.run_dataset(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
            config=RunConfig(parallelism=1),
        )

        assert result is expected
        # Three hops off the loop, one per blocking call: start the job, wait on it, fetch it.
        assert to_thread.await_count == 3
        assert len(backend.dataset_calls) == 1
        call = backend.dataset_calls[0]
        assert call["params"] == RunConfig(parallelism=1)

    def test_run_sync_uses_sync_backend_adapter(self, mocker: MockerFixture):
        expected = _empty_benchmark_result()
        backend = _FakeSyncBackend(result=expected)
        evaluator = Evaluator(client=backend)

        async def run_in_thread(func: object, *args: object, **kwargs: object) -> object:
            """Execute the submitted sync callable while recording the thread boundary."""
            return cast(Callable[..., object], func)(*args, **kwargs)

        to_thread = mocker.patch(
            "nemo_evaluator_sdk.execution.evaluator.asyncio.to_thread",
            new=mocker.AsyncMock(side_effect=run_in_thread),
        )

        result = evaluator.run_dataset_sync(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
            config=RunConfig(parallelism=1),
        )

        assert result is expected
        # Three hops off the loop, one per blocking call: start the job, wait on it, fetch it.
        assert to_thread.await_count == 3
        assert len(backend.dataset_calls) == 1
        call = backend.dataset_calls[0]
        assert call["params"] == RunConfig(parallelism=1)

    @pytest.mark.asyncio
    async def test_run_sync_uses_thread_bridge_for_sync_backend_when_loop_is_running(self):
        expected = _empty_benchmark_result()
        backend = _LoopSensitiveSyncBackend(result=expected)
        evaluator = Evaluator(client=backend)

        result = evaluator.run_dataset_sync(
            metrics=[_CustomMetric()],
            dataset=_DATASET,
            config=RunConfig(parallelism=1),
        )

        assert result is expected
        assert len(backend.dataset_calls) == 1
        call = backend.dataset_calls[0]
        assert call["params"] == RunConfig(parallelism=1)

    def test_rejects_client_with_missing_backend_method(self):
        """A client missing any contract method is rejected at construction."""
        with pytest.raises(TypeError, match="must provide callable evaluate"):
            Evaluator(client=cast(Any, _MissingEvaluateBackend()))

    def test_rejects_client_with_mixed_sync_and_async_methods(self):
        with pytest.raises(TypeError, match="mixed sync/async clients are not supported"):
            Evaluator(client=cast(Any, _MixedBackend()))

    def test_exposes_the_naming_convention(self):
        """``run*`` waits and returns a result; ``evaluate*`` returns a job.

        The bare name is the taskset path on both verbs and ``_dataset`` marks the dataset one, so
        the suffix means the same thing whichever verb it is attached to. Inverted deliberately:
        this previously asserted ``Evaluator`` had no submission method, back when submission
        existed only on the platform plugin.
        """
        evaluator = Evaluator()
        for name in ("run", "run_sync", "run_dataset", "run_dataset_sync"):
            assert hasattr(evaluator, name), name
        # The retired spellings: submit, and the suffix on the wrong verb.
        for name in ("submit", "submit_sync", "run_taskset", "run_taskset_sync", "evaluate", "evaluate_dataset"):
            assert not hasattr(evaluator, name), name

    def test_does_not_export_evaluatorv2(self):
        import nemo_evaluator_sdk.execution.evaluator as evaluator_module

        assert not hasattr(evaluator_module, "Evaluatorv2")

    def test_evaluator_module_import_does_not_require_nemo_platform(self, mocker: MockerFixture):
        evaluator_module = sys.modules.pop("nemo_evaluator_sdk.execution.evaluator", None)
        real_import = builtins.__import__

        def import_without_nemo_platform(name: str, *args: Any, **kwargs: Any) -> object:
            if name == "nemo_platform" or name.startswith("nemo_platform."):
                raise ModuleNotFoundError("No module named 'nemo_platform'", name="nemo_platform")
            if name == "nemo_evaluator" or name.startswith("nemo_evaluator."):
                raise ModuleNotFoundError("No module named 'nemo_evaluator'", name="nemo_evaluator")
            return real_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=import_without_nemo_platform)
        try:
            imported = importlib.import_module("nemo_evaluator_sdk.execution.evaluator")
            assert imported.Evaluator is not None
        finally:
            if evaluator_module is not None:
                sys.modules["nemo_evaluator_sdk.execution.evaluator"] = evaluator_module

    def test_run_sync_uses_async_backend_through_run_bridge(self):
        expected = _empty_benchmark_result()
        backend = _FakeDirectBackend(result=expected)
        evaluator = Evaluator(client=backend)

        result = evaluator.run_dataset_sync(
            metrics=[ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")],
            dataset=_DATASET,
        )

        assert result is expected
        assert len(backend.dataset_calls) == 1


class TestEvaluatorSubmit:
    """``submit`` waits on the caller's behalf, so the taskset API still hands back a result."""

    @pytest.mark.asyncio
    async def test_submit_waits_and_returns_the_result(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())
        evaluator = Evaluator(client=backend)

        result = await evaluator.run(taskset=_TASKS, target=_TARGET)

        assert result is _TASKSET_RESULT
        # Only the supplied seam is forwarded; the other is not mentioned.
        assert backend.taskset_calls == [{"taskset": _TASKS, "target": _TARGET, "config": None}]

    def test_submit_sync_waits_and_returns_the_result(self):
        backend = _FakeDirectBackend(result=_empty_benchmark_result())

        result = Evaluator(client=backend).run_sync(taskset=_TASKS, target=_TARGET)

        assert result is _TASKSET_RESULT

    @pytest.mark.asyncio
    async def test_submit_bridges_a_sync_backend_job_off_the_loop(self):
        """The sync backend's job is driven in a worker thread, not on the event loop."""
        backend = _LoopSensitiveSyncBackend(result=_empty_benchmark_result())

        result = await Evaluator(client=backend).run(taskset=_TASKS, target=_TARGET)

        assert result is _TASKSET_RESULT

    @pytest.mark.asyncio
    async def test_the_job_contracts_cannot_be_told_apart_by_isinstance(self):
        """Both contracts declare the same member names; only the flavour check separates them."""
        job = LocalJob(asyncio.create_task(_completed_taskset_run()))

        assert isinstance(job, EvaluationJob)
        assert isinstance(job, SyncEvaluationJob)
        assert inspect.iscoroutinefunction(job.get_result)
        await job.wait_until_done()


class TestLocalJob:
    """In-process execution starts on creation, so it behaves like a platform job to the caller."""

    def test_the_work_is_already_running_before_anyone_waits(self):
        started = asyncio.Event()

        async def _run() -> AgentEvalResult:
            started.set()
            return _TASKSET_RESULT

        async def _drive():
            job = LocalJob(asyncio.create_task(_run()))
            # Creating the job scheduled the work; yielding once lets it reach its first line.
            await asyncio.sleep(0)
            assert started.is_set()
            await job.wait_until_done()
            return await job.get_result()

        assert asyncio.run(_drive()) is _TASKSET_RESULT

    def test_several_evaluations_overlap_instead_of_queueing(self):
        """The reason the handle holds a task: waiting in a loop must not serialize the runs."""
        running = 0
        peak = 0

        async def _run() -> AgentEvalResult:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.02)
            running -= 1
            return _TASKSET_RESULT

        async def _drive():
            jobs = [LocalJob(asyncio.create_task(_run())) for _ in range(4)]
            for job in jobs:
                await job.wait_until_done()

        asyncio.run(_drive())
        assert peak == 4

    def test_waiting_twice_runs_the_work_once(self):
        ran = []

        async def _run() -> AgentEvalResult:
            ran.append(1)
            return _TASKSET_RESULT

        async def _drive():
            job = LocalJob(asyncio.create_task(_run()))
            await job.wait_until_done()
            await job.wait_until_done()

        asyncio.run(_drive())
        assert ran == [1]

    def test_a_failure_is_replayed_rather_than_retried(self):
        attempts = []

        async def _run() -> AgentEvalResult:
            attempts.append(1)
            raise RuntimeError("scoring blew up")

        async def _drive():
            job = LocalJob(asyncio.create_task(_run()))
            for _ in range(2):
                with pytest.raises(RuntimeError, match="scoring blew up"):
                    await job.wait_until_done()

        asyncio.run(_drive())
        assert attempts == [1]

    def test_get_result_before_the_run_finishes_says_so(self):
        async def _drive():
            job = LocalJob(asyncio.create_task(asyncio.sleep(30)))
            with pytest.raises(RuntimeError, match="has not finished yet"):
                await job.get_result()
            job._task.cancel()

        asyncio.run(_drive())

    def test_job_timeout_gives_up_waiting_without_cancelling_the_run(self):
        """A timeout means this call stopped waiting, as it would against a remote backend.

        The run is released by an event rather than a sleep, so the timeout cannot lose a race
        with a scheduling stall on a loaded machine.
        """
        finished = []

        async def _drive():
            release = asyncio.Event()

            async def _run() -> AgentEvalResult:
                await release.wait()
                finished.append(1)
                return _TASKSET_RESULT

            job = LocalJob(asyncio.create_task(_run()))
            with pytest.raises(TimeoutError):
                await job.wait_until_done(job_timeout_seconds=0.01)
            assert finished == []  # the wait gave up; the run did not

            release.set()
            # The run survived the abandoned wait, so a later wait still collects it.
            await job.wait_until_done()
            return await job.get_result()

        assert asyncio.run(_drive()) is _TASKSET_RESULT
        assert finished == [1]

    def test_concurrent_waits_run_the_work_once(self):
        """Several waiters share the one task rather than each starting their own."""
        runs = []

        async def _run() -> AgentEvalResult:
            runs.append(1)
            await asyncio.sleep(0)
            return _TASKSET_RESULT

        async def _drive():
            job = LocalJob(asyncio.create_task(_run()))
            await asyncio.gather(*(job.wait_until_done() for _ in range(5)))
            return await job.get_result()

        assert asyncio.run(_drive()) is _TASKSET_RESULT
        assert runs == [1]

    def test_an_infinite_timeout_means_no_ceiling(self):
        async def _drive():
            job = LocalJob(asyncio.create_task(_completed_taskset_run()))
            await job.wait_until_done(job_timeout_seconds=float("inf"))
            return await job.get_result()

        assert asyncio.run(_drive()) is _TASKSET_RESULT

    @pytest.mark.asyncio
    async def test_the_local_backend_validates_before_starting_anything(self):
        """A malformed taskset fails when the evaluation is requested, as it does remotely."""
        with pytest.raises(ValueError, match="at least one task is required"):
            await LocalBackend().evaluate(taskset=[], target=None)  # ty: ignore[invalid-argument-type]

    @pytest.mark.asyncio
    async def test_the_local_backend_requires_exactly_one_seam(self):
        with pytest.raises(ValueError, match="exactly one of trials or target"):
            await LocalBackend().evaluate(taskset=[_agent_task()], trials=None, target=None)  # ty: ignore[no-matching-overload]


class TestSeamValidation:
    """Every forwarder validates before it branches.

    Branching on ``trials is not None`` alone would let a call carrying both seams silently drop
    the target instead of rejecting it — the failure this guards.
    """

    @pytest.mark.asyncio
    async def test_submit_rejects_both_seams(self):
        evaluator = Evaluator(client=_FakeDirectBackend(result=_empty_benchmark_result()))

        with pytest.raises(ValueError, match="exactly one of trials or target"):
            await evaluator.run(taskset=_TASKS, trials=[], target=_TARGET)  # ty: ignore[no-matching-overload]

    def test_submit_sync_rejects_both_seams(self):
        evaluator = Evaluator(client=_FakeDirectBackend(result=_empty_benchmark_result()))

        with pytest.raises(ValueError, match="exactly one of trials or target"):
            evaluator.run_sync(taskset=_TASKS, trials=[], target=_TARGET)  # ty: ignore[no-matching-overload]

    @pytest.mark.asyncio
    async def test_local_backend_rejects_both_seams(self):
        with pytest.raises(ValueError, match="exactly one of trials or target"):
            await LocalBackend().evaluate(taskset=_TASKS, trials=[], target=_TARGET)  # ty: ignore[no-matching-overload]
