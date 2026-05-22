# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from typing import Any

import pytest
from jinja2.exceptions import UndefinedError
from nemo_evaluator_sdk import inference
from nemo_evaluator_sdk.execution.values import EvaluationError, EvaluationPhase
from nemo_evaluator_sdk.values import MetricInput, MetricOutput, MetricOutputSpec, MetricResult, Model
from nmp.evaluator.app.values import BenchmarkOfflineJob, BenchmarkOnlineJob
from nmp.evaluator.tasks.evaluate_benchmark import __main__ as benchmark_task
from pytest_mock import MockerFixture


def _metric_result(name: str, value: float) -> MetricResult:
    return MetricResult(outputs=[MetricOutput(name=name, value=value)])


def _output_spec(name: str) -> list[MetricOutputSpec]:
    return [MetricOutputSpec.continuous_score(name)]


@pytest.fixture
def test_offline_job() -> BenchmarkOfflineJob:
    return BenchmarkOfflineJob.model_validate(
        {
            "benchmark": {
                "name": "test-benchmark",
                "dataset": "test-workspace/test-dataset",
                "metrics": [
                    {
                        "metric_ref": "default/exact-match",
                        "metric": {
                            "type": "exact-match",
                            "reference": "{{item.expected}}",
                        },
                    },
                    {
                        "metric_ref": "default/string-check",
                        "metric": {
                            "type": "string-check",
                            "operation": "startswith",
                            "left_template": "{{item.actual}}",
                            "right_template": "{{item.expected}}",
                        },
                    },
                ],
            },
        }
    )


@pytest.fixture
def test_online_job() -> BenchmarkOnlineJob:
    return BenchmarkOnlineJob.model_validate(
        {
            "benchmark": {
                "name": "test-benchmark",
                "dataset": "test-workspace/test-dataset",
                "metrics": [
                    {
                        "metric_ref": "default/exact-match",
                        "metric": {
                            "type": "exact-match",
                            "reference": "{{item.expected}}",
                        },
                    },
                    {
                        "metric_ref": "default/string-check",
                        "metric": {
                            "type": "string-check",
                            "operation": "startswith",
                            "left_template": "{{item.actual}}",
                            "right_template": "{{item.expected}}",
                        },
                    },
                ],
            },
            "model": {"url": "http://nim.test/v1", "name": "my/model"},
            "prompt_template": "{{item.input}}",
        }
    )


@pytest.fixture
def test_online_job_f1() -> BenchmarkOnlineJob:
    return BenchmarkOnlineJob.model_validate(
        {
            "benchmark": {
                "name": "partial-failure-benchmark",
                "dataset": "test-workspace/test-dataset",
                "metrics": [
                    {
                        "metric_ref": "default/f1-metric",
                        "metric": {
                            "type": "f1",
                            "reference": "{{item.reference}}",
                            "candidate": "{{item.candidate}}",
                        },
                    },
                ],
            },
            "model": {
                "url": "http://model.ai",
                "name": "my-model",
            },
            "prompt_template": {},
            "params": {"ignore_request_failure": True},
        }
    )


@pytest.mark.asyncio
async def test_evaluate_benchmark_accumulates_requests_across_metrics(tmp_path, monkeypatch, test_offline_job):
    monkeypatch.setattr(benchmark_task, "_load_dataset_items", lambda *args, **kwargs: [{"id": 1}])

    class _FakeMetric:
        def __init__(self, metric_name: str):
            self._metric_name = metric_name

        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec(self._metric_name)

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            requests_log = inference.requests_log_var.get()
            requests_log.append({"metric": self._metric_name, "item_id": input.row.data["id"]})
            return _metric_result(self._metric_name, 1.0)

    async def _fake_new_metric(metric_config, *args, **kwargs):
        return _FakeMetric(str(metric_config.type.value))

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    await benchmark_task.evaluate_benchmark(job=test_offline_job, results_dir=str(tmp_path))

    row_scores_path = tmp_path / "row-scores.jsonl"
    lines = [line for line in row_scores_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row["metrics"]) == {"default/exact-match", "default/string-check"}
    assert row["requests"] == [
        {"metric": "exact-match", "item_id": 1},
        {"metric": "string-check", "item_id": 1},
    ]


@pytest.mark.asyncio
async def test_evaluate_benchmark_offline_errors_when_metric_fails(tmp_path, monkeypatch, test_offline_job):
    # ignore_request_failure is not supported for offline jobs
    monkeypatch.setattr(benchmark_task, "_load_dataset_items", lambda *args, **kwargs: [{"id": 1}])

    class _FakeMetric:
        def __init__(self, metric_name: str):
            self._metric_name = metric_name

        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec(self._metric_name)

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            requests_log = inference.requests_log_var.get()
            requests_log.append({"metric": self._metric_name, "item_id": input.row.data["id"]})
            if self._metric_name == "string-check":
                raise RuntimeError("boom")
            return _metric_result(self._metric_name, 1.0)

    async def _fake_new_metric(metric_config, *args, **kwargs):
        return _FakeMetric(str(metric_config.type.value))

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    with pytest.raises(EvaluationError, match="boom") as exc:
        await benchmark_task.evaluate_benchmark(job=test_offline_job, results_dir=str(tmp_path))
    assert exc.value.index == 0
    assert exc.value.metric_key == "default/string-check"
    assert exc.value.phase is EvaluationPhase.METRIC_SCORING
    assert exc.value.message == "boom"


@pytest.mark.asyncio
async def test_evaluate_benchmark_accumulates_requests_when_metric_fails(tmp_path, monkeypatch, test_online_job):
    test_online_job.params.ignore_request_failure = True
    monkeypatch.setattr(benchmark_task, "_load_dataset_items", lambda *args, **kwargs: [{"id": 1}])

    class _FakeMetric:
        def __init__(self, metric_name: str):
            self._metric_name = metric_name

        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec(self._metric_name)

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            requests_log = inference.requests_log_var.get()
            requests_log.append({"metric": self._metric_name, "item_id": input.row.data["id"]})
            if self._metric_name == "string-check":
                raise RuntimeError("boom")
            return _metric_result(self._metric_name, 1.0)

    async def _fake_new_metric(metric_config, *args, **kwargs):
        return _FakeMetric(str(metric_config.type.value))

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    await benchmark_task.evaluate_benchmark(job=test_online_job, results_dir=str(tmp_path))

    row_scores_path = tmp_path / "row-scores.jsonl"
    lines = [line for line in row_scores_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row["metrics"]) == {"default/exact-match", "default/string-check"}
    assert row["requests"] == [
        {"metric": "exact-match", "item_id": 1},
        {"metric": "string-check", "item_id": 1},
    ]


@pytest.mark.asyncio
async def test_evaluate_benchmark_offline_progress_tracking_completes(
    tmp_path,
    monkeypatch,
    mocker: MockerFixture,
    test_offline_job,
):
    monkeypatch.setattr(
        benchmark_task,
        "_load_dataset_items",
        lambda *args, **kwargs: [{"id": 1, "expected": "yes"}, {"id": 2, "expected": "yes"}],
    )

    class _FakeMetric:
        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec("exact-match")

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            del input
            return _metric_result("exact-match", 1.0)

    async def _fake_new_metric(*_args, **_kwargs):
        return _FakeMetric()

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    progress_tracking = mocker.Mock()
    progress_tracking.interval = 5
    progress_tracking.total_samples = None

    result = await benchmark_task.evaluate_benchmark(
        job=test_offline_job,
        results_dir=str(tmp_path),
        progress_tracking=progress_tracking,
    )

    assert len(result.results) == 2, result.results
    assert progress_tracking.total_samples == 2
    progress_tracking.increment_samples_processed.assert_called_once_with(2)
    progress_tracking.update_progress.assert_called_once_with(100)


@pytest.mark.asyncio
async def test_evaluate_benchmark_duplicate_metric_types_use_unique_metric_refs(tmp_path, monkeypatch):
    job = BenchmarkOfflineJob.model_validate(
        {
            "benchmark": {
                "name": "duplicate-type-benchmark",
                "dataset": "test-workspace/test-dataset",
                "metrics": [
                    {
                        "metric_ref": "default/exact-match-1",
                        "metric": {"type": "exact-match", "reference": "{{item.expected}}"},
                    },
                    {
                        "metric_ref": "default/exact-match-2",
                        "metric": {"type": "exact-match", "reference": "{{item.expected_alt}}"},
                    },
                ],
            },
        }
    )
    monkeypatch.setattr(
        benchmark_task,
        "_load_dataset_items",
        lambda *args, **kwargs: [{"id": 1, "expected": "yes", "expected_alt": "yes"}],
    )

    class _FakeMetric:
        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec("score")

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            del input
            return _metric_result("score", 1.0)

    async def _fake_new_metric(*_args, **_kwargs):
        return _FakeMetric()

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    result = await benchmark_task.evaluate_benchmark(job=job, results_dir=str(tmp_path))

    metric_refs: list[str] = []
    for metric_result in result.results:
        assert metric_result.metric is not None
        metric_refs.append(metric_result.metric.root)
    assert metric_refs == ["default/exact-match-1", "default/exact-match-2"]
    row_scores_path = tmp_path / "row-scores.jsonl"
    lines = [line for line in row_scores_path.read_text().splitlines() if line.strip()]
    row = json.loads(lines[0])
    assert set(row["metrics"].keys()) == {"default/exact-match-1", "default/exact-match-2"}


@pytest.mark.asyncio
async def test_evaluate_benchmark_partial_failures_keep_nan_under_metric_score_name(
    tmp_path, monkeypatch, test_online_job_f1
):
    monkeypatch.setattr(
        benchmark_task,
        "_load_dataset_items",
        lambda *args, **kwargs: [
            {"id": 1, "reference": "a", "candidate": "a"},
            {"id": 2, "reference": "b", "candidate": "b"},
        ],
    )

    class _FlakyMetric:
        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec("f1_score")

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            if input.row.data["id"] == 2:
                raise RuntimeError("transient")
            return _metric_result("f1_score", 1.0)

    async def _fake_new_metric(*_args, **_kwargs):
        return _FlakyMetric()

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    result = await benchmark_task.evaluate_benchmark(job=test_online_job_f1, results_dir=str(tmp_path))

    assert len(result.results) == 1
    aggregated_scores = result.results[0].scores
    assert len(aggregated_scores) == 1
    assert aggregated_scores[0].name == "f1_score"
    assert aggregated_scores[0].count == 1
    assert aggregated_scores[0].nan_count == 1


@pytest.mark.asyncio
async def test_evaluate_benchmark_all_failures_use_declared_score_names(tmp_path, monkeypatch, test_online_job_f1):
    monkeypatch.setattr(
        benchmark_task,
        "_load_dataset_items",
        lambda *args, **kwargs: [
            {"id": 1, "reference": "a", "candidate": "a"},
            {"id": 2, "reference": "b", "candidate": "b"},
        ],
    )

    class _AlwaysFailMetric:
        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec("f1_score")

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            del input
            raise RuntimeError("transient")

    async def _fake_new_metric(*_args, **_kwargs):
        return _AlwaysFailMetric()

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    result = await benchmark_task.evaluate_benchmark(job=test_online_job_f1, results_dir=str(tmp_path))
    aggregated_scores = result.results[0].scores
    assert len(aggregated_scores) == 1
    assert aggregated_scores[0].name == "f1_score"
    assert aggregated_scores[0].count == 0
    assert aggregated_scores[0].nan_count == 2


@pytest.mark.asyncio
async def test_online_benchmark_reuses_single_inference_sample_across_metrics(tmp_path, monkeypatch, test_online_job):
    monkeypatch.setattr(
        benchmark_task,
        "_load_dataset_items",
        lambda *args, **kwargs: [{"id": 1, "input": "prompt", "expected": "answer"}],
    )

    inference_call_count = 0

    async def _fake_inference_fn(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal inference_call_count
        inference_call_count += 1
        return {"choices": [{"message": {"role": "assistant", "content": "answer"}}]}

    class _FakeMetric:
        def __init__(self, metric_name: str):
            self._metric_name = metric_name

        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec(self._metric_name)

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            del input
            return _metric_result(self._metric_name, 1.0)

    async def _fake_new_metric(metric_config, *_args, **_kwargs):
        return _FakeMetric(str(metric_config.type.value))

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    await benchmark_task.evaluate_benchmark(
        job=test_online_job,
        results_dir=str(tmp_path),
        inference_fn=_fake_inference_fn,
    )

    assert inference_call_count == 1


@pytest.mark.asyncio
async def test_online_benchmark_streams_samples_to_metric_workers(tmp_path, monkeypatch, test_online_job):
    test_online_job.params.parallelism = 1

    monkeypatch.setattr(
        benchmark_task,
        "_load_dataset_items",
        lambda *args, **kwargs: [
            {"id": 1, "input": "prompt-1", "expected": "answer"},
            {"id": 2, "input": "prompt-2", "expected": "answer"},
        ],
    )

    metric_started = asyncio.Event()
    inference_call_count = 0

    async def _fake_inference_fn(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal inference_call_count
        inference_call_count += 1
        if inference_call_count == 2:
            await metric_started.wait()
        return {"choices": [{"message": {"role": "assistant", "content": "answer"}}]}

    class _FakeMetric:
        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec("exact-match")

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            del input
            metric_started.set()
            return _metric_result("exact-match", 1.0)

    async def _fake_new_metric(*_args, **_kwargs):
        return _FakeMetric()

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    result = await asyncio.wait_for(
        benchmark_task.evaluate_benchmark(
            job=test_online_job, results_dir=str(tmp_path), inference_fn=_fake_inference_fn
        ),
        timeout=2.0,
    )
    assert len(result.results) == 2, result.results


@pytest.mark.asyncio
async def test_evaluate_offline_benchmark_surfaces_strict_metric_error_context(tmp_path, monkeypatch, test_offline_job):
    monkeypatch.setattr(benchmark_task, "_load_dataset_items", lambda *args, **kwargs: [{"id": 1}])

    class _FailingMetric:
        def output_spec(self) -> list[MetricOutputSpec]:
            return _output_spec("exact-match")

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            del input
            raise ValueError("metric exploded")

    async def _fake_new_metric(*_args, **_kwargs):
        return _FailingMetric()

    monkeypatch.setattr(benchmark_task, "new_metric", _fake_new_metric)

    with pytest.raises(EvaluationError, match="metric exploded") as exc:
        await benchmark_task.evaluate_benchmark(job=test_offline_job, results_dir=str(tmp_path))
    assert exc.value.index == 0
    assert exc.value.metric_key == "default/exact-match"
    assert exc.value.phase is EvaluationPhase.METRIC_SCORING
    assert exc.value.message == "metric exploded"

    # One metric still uses the same typed benchmark strict-mode contract.
    test_offline_job.benchmark.metrics = test_offline_job.benchmark.metrics[:1]
    with pytest.raises(EvaluationError, match="metric exploded") as single_exc:
        await benchmark_task.evaluate_benchmark(job=test_offline_job, results_dir=str(tmp_path))
    assert single_exc.value.metric_key == "default/exact-match"


@pytest.mark.asyncio
async def test_evaluate_online_benchmark_surfaces_strict_sample_generation_context(
    tmp_path, monkeypatch, test_online_job
):
    monkeypatch.setattr(benchmark_task, "_load_dataset_items", lambda *args, **kwargs: [{"id": 1}])

    with pytest.raises(EvaluationError, match="'dict object' has no attribute 'input'") as exc:
        await benchmark_task.evaluate_benchmark(job=test_online_job, results_dir=str(tmp_path))
    assert exc.value.index == 0
    assert exc.value.metric_key is None
    assert exc.value.phase is EvaluationPhase.SAMPLE_GENERATION
    assert isinstance(exc.value.__cause__, UndefinedError)


@pytest.mark.asyncio
async def test_evaluate_benchmark_attaches_platform_headers_to_judge_model(
    tmp_path,
    monkeypatch,
    mocker: MockerFixture,
):
    job = BenchmarkOfflineJob.model_validate(
        {
            "benchmark": {
                "name": "judge-benchmark",
                "dataset": "test-workspace/test-dataset",
                "metrics": [
                    {
                        "metric_ref": "default/llm-judge",
                        "metric": {
                            "type": "llm-judge",
                            "model": {
                                "url": "http://nemo-platform-api.default.svc.cluster.local/v1/chat/completions",
                                "name": "judge-model",
                            },
                            "scores": [
                                {
                                    "name": "quality",
                                    "minimum": 1,
                                    "maximum": 5,
                                    "parser": {"type": "json", "json_path": "quality"},
                                }
                            ],
                        },
                    }
                ],
            }
        }
    )
    monkeypatch.setattr(benchmark_task, "_load_dataset_items", lambda *args, **kwargs: [{"prompt": "hi"}])
    captured_model_headers: list[dict[str, str] | None] = []

    async def capturing_inference(
        model: Model,
        request: dict,
        max_retries: int | None,
        **kwargs,
    ) -> dict:
        captured_model_headers.append(model.default_headers)
        return {"choices": [{"message": {"content": '{"quality": 5}'}}]}

    mocker.patch(
        "nmp.evaluator.app.metrics.metric.app_inference.get_platform_headers",
        return_value={"X-NMP-Principal-Id": "service:evaluator"},
    )

    await benchmark_task.evaluate_benchmark(job=job, results_dir=str(tmp_path), inference_fn=capturing_inference)

    assert captured_model_headers
    assert captured_model_headers == [{"X-NMP-Principal-Id": "service:evaluator"}] * len(captured_model_headers)
