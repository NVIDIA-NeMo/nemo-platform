# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_evaluator_sdk.execution.values import EvaluationError, EvaluationPhase
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values import AggregateRangeScore
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult as SDKBenchmarkEvaluationResult
from nmp.common.jobs.constants import NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.evaluator.app.values import (
    BenchmarkEvaluationResult,
    BenchmarkMetricResult,
    BenchmarkOfflineJob,
    BenchmarkOnlineAgentJob,
    BenchmarkOnlineJob,
)
from nmp.evaluator.tasks.evaluate_benchmark.__main__ import (
    _load_dataset_items,
    benchmark_evaluation_entrypoint,
    benchmark_evaluation_entrypoint_args,
    evaluate_benchmark,
    main,
)
from pytest_mock import MockerFixture


def _write_benchmark_job_config(tmp_path: Path) -> Path:
    """Write a minimal benchmark task config file for CLI-oriented tests."""
    config_path = tmp_path / "benchmark-job.json"
    config_path.write_text("{}")
    return config_path


class TestEvaluateBenchmark:
    def test_load_dataset_items_defaults_optional_metric_fields(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Benchmark dataset loading should map canonical fields and default optional metric fields."""
        job = BenchmarkOnlineJob.model_validate(
            {
                "benchmark": {
                    "name": "pipeline-benchmark",
                    "dataset": "test-workspace/test-dataset",
                    "metrics": [
                        {
                            "metric_ref": "default/llm-judge",
                            "metric": {
                                "type": "llm-judge",
                                "model": {"url": "http://nim.test/v1", "name": "judge", "format": "openai"},
                                "optional_fields": ["reference"],
                                "scores": [
                                    {
                                        "name": "score",
                                        "description": "Score from 1-5",
                                        "minimum": 1,
                                        "maximum": 5,
                                        "parser": {"type": "json", "json_path": "score"},
                                    }
                                ],
                                "prompt_template": {
                                    "messages": [
                                        {"role": "user", "content": "Q: {{item.input}}\nR: {{item.reference}}"}
                                    ]
                                },
                            },
                        }
                    ],
                    "field_mapping": {"input": "question"},
                },
                "model": {"url": "http://nim.test/v1", "name": "my/model"},
                "prompt_template": "{{item.input}}",
            }
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.load_dataset_from_ref_as_dicts",
            return_value=[{"question": "hello"}],
        )

        assert _load_dataset_items(job, dataset_dir=str(tmp_path)) == [
            {"question": "hello", "input": "hello", "reference": ""}
        ]

    def test_load_dataset_items_defaults_to_runtime_job_storage(
        self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Benchmark dataset loading should read from runtime job storage by default."""
        job = BenchmarkOfflineJob.model_validate(
            {
                "benchmark": {
                    "name": "test-benchmark",
                    "dataset": "test-workspace/test-dataset",
                    "metrics": [
                        {
                            "metric_ref": "default/exact-match",
                            "metric": {"type": "exact-match", "reference": "{{item.expected}}"},
                        }
                    ],
                },
            }
        )
        storage_dir = tmp_path / "job-storage"
        monkeypatch.setenv(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, str(storage_dir))
        load_dataset = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.load_dataset_from_ref_as_dicts",
            return_value=[{"input": "hello"}],
        )

        assert _load_dataset_items(job) == [{"input": "hello"}]
        load_dataset.assert_called_once_with("test-workspace/test-dataset", base_dir=str(storage_dir / "datasets"))

    @pytest.mark.asyncio
    async def test_defaults_missing_params_before_sdk_execution(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Missing job params should be normalized to default offline params."""
        job = BenchmarkOfflineJob.model_validate(
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
                        }
                    ],
                },
                "params": None,
            }
        )
        metric = mocker.Mock()
        metric.score_names.return_value = ["exact-match"]
        service_result = mocker.Mock(results=[])

        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__._load_dataset_items",
            return_value=[{"id": 1}],
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.new_metric",
            new_callable=mocker.AsyncMock,
            return_value=metric,
        )
        sdk_evaluate = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.sdk_evaluate_benchmark",
            new_callable=mocker.AsyncMock,
            return_value=mocker.Mock(row_scores=[]),
        )
        mocker.patch(
            "nmp.evaluator.app.values.benchmarks_job.BenchmarkEvaluationResult.from_sdk_results",
            return_value=service_result,
        )
        mocker.patch("nmp.evaluator.tasks.evaluate_benchmark.__main__.job_artifacts_dump")

        result = await evaluate_benchmark(job, str(tmp_path))

        assert result is service_result
        assert sdk_evaluate.await_args.kwargs["params"] is not None
        assert sdk_evaluate.await_args.kwargs["params"].parallelism == 8
        assert sdk_evaluate.await_args.kwargs["params"].limit_samples is None

    @pytest.mark.asyncio
    async def test_logs_structured_benchmark_error_context(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Typed benchmark SDK failures should be logged with row and metric context."""
        job = BenchmarkOfflineJob.model_validate(
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
                        }
                    ],
                }
            }
        )
        metric = mocker.Mock()
        metric.score_names.return_value = ["exact-match"]
        benchmark_error = EvaluationError(
            index=3,
            message="metric exploded",
            phase=EvaluationPhase.METRIC_SCORING,
            metric_key="default/exact-match",
        )

        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__._load_dataset_items",
            return_value=[{"id": 1}],
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.new_metric",
            new_callable=mocker.AsyncMock,
            return_value=metric,
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.sdk_evaluate_benchmark",
            new_callable=mocker.AsyncMock,
            side_effect=benchmark_error,
        )
        log_exception = mocker.patch("nmp.evaluator.tasks.evaluate_benchmark.__main__.log.exception")

        with pytest.raises(EvaluationError) as exc_info:
            await evaluate_benchmark(job, str(tmp_path))

        assert exc_info.value is benchmark_error
        log_exception.assert_called_once_with(
            "Benchmark evaluation failed",
            extra={
                "phase": "metric_scoring",
                "metric_key": "default/exact-match",
                "row_index": 3,
                "error": "metric exploded",
            },
        )

    @pytest.mark.asyncio
    async def test_agent_benchmark_passes_platform_headers_to_agent_inference(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Platform headers from agent URL should reach the agent inference function."""
        job = BenchmarkOnlineAgentJob.model_validate(
            {
                "benchmark": {
                    "name": "agent-benchmark",
                    "dataset": "test-workspace/test-dataset",
                    "metrics": [
                        {
                            "metric_ref": "default/agent-score",
                            "metric": {"type": "exact-match", "reference": "{{item.expected}}"},
                        }
                    ],
                },
                "agent": {
                    "url": "http://nemo-platform-api.default.svc.cluster.local/v1/agents/test",
                    "name": "test-agent",
                    "format": "generic",
                    "body": {"prompt": "{{ prompt }}"},
                    "response_path": "$.answer",
                },
                "prompt_template": "{{item.prompt}}",
            }
        )
        headers = {"X-NMP-Principal-Id": "service:evaluator"}
        captured_headers: list[dict[str, str] | None] = []

        class _FakeMetric:
            """Metric test double that returns a fixed score."""

            def output_spec(self) -> list[MetricOutputSpec]:
                """Return the outputs exposed by this metric."""
                return [MetricOutputSpec.continuous_score("score")]

            async def compute_scores(self, input: MetricInput) -> MetricResult:
                """Return one fixed metric score."""
                del input
                return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])

        async def _agent_inference(
            agent,
            request,
            max_retries,
            default_headers=None,
            **kwargs,
        ) -> dict:
            """Capture forwarded default headers and return an OpenAI-style response."""
            captured_headers.append(default_headers)
            return {"choices": [{"message": {"content": "ok"}}]}

        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__._load_dataset_items",
            return_value=[{"prompt": "hi", "expected": "ok"}],
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.new_metric",
            new_callable=mocker.AsyncMock,
            return_value=_FakeMetric(),
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.get_platform_headers",
            return_value=headers,
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.make_agent_inference_request",
            side_effect=_agent_inference,
        )

        await evaluate_benchmark(job, str(tmp_path))

        assert captured_headers == [headers]

    def test_from_sdk_results_strips_metric_namespace_and_binds_metric_ref(self) -> None:
        """SDK benchmark results should be projected onto the service wire shape."""
        job = BenchmarkOfflineJob.model_validate(
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
                        }
                    ],
                }
            }
        )
        sdk_result = SDKBenchmarkEvaluationResult.model_validate(
            {
                "row_scores": [],
                "aggregate_scores": {"scores": []},
                "per_metric": {
                    "default/exact-match": {
                        "row_scores": [],
                        "aggregate_scores": {
                            "scores": [
                                {
                                    "name": "default/exact-match.score",
                                    "count": 1,
                                    "nan_count": 0,
                                    "sum": 1.0,
                                    "mean": 1.0,
                                    "min": 1.0,
                                    "max": 1.0,
                                    "variance": 0.0,
                                    "std_dev": 0.0,
                                    "percentiles": {
                                        "p10": 1.0,
                                        "p20": 1.0,
                                        "p30": 1.0,
                                        "p40": 1.0,
                                        "p50": 1.0,
                                        "p60": 1.0,
                                        "p70": 1.0,
                                        "p80": 1.0,
                                        "p90": 1.0,
                                        "p100": 1.0,
                                    },
                                    "histogram": {"bins": []},
                                }
                            ]
                        },
                    }
                },
            }
        )

        result = BenchmarkEvaluationResult.from_sdk_results(sdk_result, job.benchmark.metrics)
        sdk_score = sdk_result.per_metric["default/exact-match"].aggregate_scores.scores[0]
        assert isinstance(sdk_score, AggregateRangeScore)

        assert result == BenchmarkEvaluationResult(
            results=[
                BenchmarkMetricResult(
                    metric=job.benchmark.metrics[0].metric_ref,
                    scores=[
                        AggregateRangeScore(
                            name="score",
                            count=1,
                            nan_count=0,
                            sum=1.0,
                            mean=1.0,
                            min=1.0,
                            max=1.0,
                            variance=0.0,
                            std_dev=0.0,
                            percentiles=sdk_score.percentiles,
                            histogram=sdk_score.histogram,
                        )
                    ],
                )
            ]
        )


class TestMain:
    @pytest.mark.asyncio
    async def test_defaults_to_job_runtime_environment(
        self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Main should use job runtime env vars when argv omits config and results paths."""
        config_file = _write_benchmark_job_config(tmp_path)
        storage_dir = tmp_path / "job-storage"
        expected_results_dir = str(storage_dir / "results")
        evaluation_result = mocker.Mock(results=[mocker.Mock(scores=[mocker.Mock(count=1)])])

        monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_file))
        monkeypatch.setenv(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, str(storage_dir))

        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.BenchmarkJobAdapter.validate_python",
            return_value=mocker.Mock(),
        )
        evaluate = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.evaluate_benchmark",
            new_callable=mocker.AsyncMock,
            return_value=evaluation_result,
        )

        assert await main(["--skip-upload-results"]) == 0
        evaluate.assert_awaited_once_with(mocker.ANY, expected_results_dir, None)

    @pytest.mark.asyncio
    async def test_uploads_results_and_builds_results_handler_config(
        self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Main should load env-backed results config and upload results on success."""
        config_file = _write_benchmark_job_config(tmp_path)
        results_dir = tmp_path / "results"
        results_config = mocker.Mock(NEMO_JOB_ID="job-123", NEMO_JOB_WORKSPACE="workspace")
        progress_tracking = mocker.Mock()
        evaluation_result = mocker.Mock(results=[mocker.Mock(scores=[mocker.Mock(count=1)])])
        sdk = mocker.Mock()
        monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_file))
        monkeypatch.setenv(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, str(tmp_path))

        results_handler_cls = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.ResultsHandlerConfig",
            return_value=results_config,
        )
        progress_tracking_cls = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.ProgressTracking",
            return_value=progress_tracking,
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.BenchmarkJobAdapter.validate_python",
            return_value=mocker.Mock(),
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.evaluate_benchmark",
            new_callable=mocker.AsyncMock,
            return_value=evaluation_result,
        )
        handle_results = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.handle_results_async",
            new_callable=mocker.AsyncMock,
        )
        get_sdk = mocker.patch(
            "nmp.evaluator.tasks.evaluate_benchmark.__main__.get_async_platform_sdk",
            return_value=sdk,
        )

        exit_code = await main(
            [
                "--progress-tracking-url",
                "https://callback.example.test",
                "--progress-tracking-interval",
                "25",
                "--progress-tracking-interval-seconds",
                "30",
            ]
        )

        assert exit_code == 0
        results_handler_cls.assert_called_once_with()
        progress_tracking_cls.assert_called_once_with("https://callback.example.test", 25, 30)
        get_sdk.assert_called_once_with()
        handle_results.assert_awaited_once_with(
            mocker.ANY,
            results_config,
            str(results_dir),
            sdk=sdk,
        )
        progress_tracking.stop.assert_called_once_with()


class TestBenchmarkEvaluationEntrypoint:
    def test_returns_python_module_command(self):
        assert benchmark_evaluation_entrypoint() == ["python", "-m", "nmp.evaluator.tasks.evaluate_benchmark"]


class TestBenchmarkEvaluationEntrypointArgs:
    def test_defaults_to_job_runtime_environment(self):
        assert benchmark_evaluation_entrypoint_args() == []

    def test_includes_progress_tracking_options(self):
        assert benchmark_evaluation_entrypoint_args(
            progress_tracking_url="https://callback.example.test",
            progress_tracking_interval=25,
        ) == [
            "--progress-tracking-url",
            "https://callback.example.test",
            "--progress-tracking-interval",
            "25",
        ]
