# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the evaluate_metric task.

These tests verify that the evaluate_metric function correctly:
- Evaluates metrics with mocked model inference
- Writes evaluation artifacts (job.json, results.jsonl, evaluation_results.json)
- Aggregates scores across samples
- Handles offline and online evaluation modes
- Properly handles inference failures with ignore_request_failure flag
- Loads datasets from FilesetRef (downloaded files) as well as inline rows

Uses create_test_client for testing the results upload flow when
combined with handle_results.
"""

import json
from pathlib import Path

import pytest
from nemo_evaluator_sdk.execution.values import EvaluationError, EvaluationPhase
from nemo_evaluator_sdk.inference import InferenceFn
from nemo_evaluator_sdk.values import (
    AggregatedMetricResult,
    AggregateRangeScore,
    DatasetRows,
    Model,
)
from nemo_platform import NeMoPlatform
from nmp.common.jobs.constants import NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.evaluator.app.jobs.constants import (
    EVALUATION_RESULTS_AGG_SCORES_FILE_NAME,
    EVALUATION_RESULTS_ROW_SCORES_FILE_NAME,
)
from nmp.evaluator.app.jobs.metric_results import ResultsHandlerConfig, handle_results_async
from nmp.evaluator.app.values import MetricJobAdapter
from nmp.evaluator.tasks.evaluate_metric.__main__ import (
    _json_default,
    _load_dataset_items,
    evaluate_metric,
    main,
    metric_evaluation_entrypoint,
    metric_evaluation_entrypoint_args,
    no_aggregated_metric_scores,
    run,
)
from pytest_mock import MockerFixture

# Test workspace - must match conftest.py
TEST_WORKSPACE = "test-workspace"
INLINE_DATASET_FILENAME = "dataset.json"


# =============================================================================
# Mock Inference Helpers
# =============================================================================


def make_mock_inference(response: dict) -> InferenceFn:
    """Create a mock inference function that returns a fixed response."""

    async def mock_inference(
        model: Model,
        request: dict,
        max_retries: int | None,
        **kwargs,
    ) -> dict:
        return response

    return mock_inference


def make_mock_inference_with_side_effects(responses: list[dict | Exception]) -> InferenceFn:
    """Create a mock inference function that returns responses in sequence or raises exceptions."""
    call_count = 0

    async def mock_inference(
        model: Model,
        request: dict,
        max_retries: int | None,
        **kwargs,
    ) -> dict:
        nonlocal call_count
        response = responses[call_count % len(responses)]
        call_count += 1
        if isinstance(response, Exception):
            raise response
        return response

    return mock_inference


def make_failing_inference(error: Exception) -> InferenceFn:
    """Create a mock inference function that always raises an exception."""

    async def mock_inference(
        model: Model,
        request: dict,
        max_retries: int | None,
        **kwargs,
    ) -> dict:
        raise error

    return mock_inference


# =============================================================================
# Test Data
# =============================================================================


def create_offline_llm_judge_job() -> dict:
    """Create an offline LLM Judge metric job config."""
    return {
        "dataset": {
            "rows": [
                {"input": "What is Python?", "output": "A programming language"},
                {"input": "Explain quantum computing", "output": "Complex physics stuff"},
            ],
        },
        "metric": {
            "type": "llm-judge",
            "model": {
                "url": "http://mock-judge:8000/v1/chat/completions",
                "name": "mock-judge-model",
            },
            "scores": [
                {
                    "name": "length",
                    "rubric": [
                        {"label": "short", "value": 0},
                        {"label": "long", "value": 1},
                    ],
                }
            ],
        },
        "params": {
            "parallelism": 1,
        },
    }


def create_online_exact_match_job() -> dict:
    """Create an online evaluation job with exact-match metric."""
    return {
        "model": {
            "name": "test-model",
            "url": "http://mock-model:8000/v1/chat/completions",
            "format": "nim",
        },
        "dataset": {
            "rows": [
                {"input": "What is 1+1?", "expected": "2"},
                {"input": "What is 2+2?", "expected": "4"},
            ],
        },
        "prompt_template": {"messages": [{"role": "user", "content": "{{input}}"}]},
        "metric": {
            "type": "exact-match",
            "name": "qa-exact-match",
            "reference": "{{item.expected}}",
        },
        "params": {
            "parallelism": 1,
            "max_retries": 1,
        },
    }


def create_fileset_urn_llm_judge_job(fileset_urn: str) -> dict:
    """Create an offline LLM Judge job that uses FilesetRef dataset.

    This simulates the scenario where a dataset has been downloaded
    from a fileset to the JOB_DATASET_DIR.
    """
    return {
        "dataset": fileset_urn,  # FilesetRef as string
        "metric": {
            "type": "llm-judge",
            "model": {
                "url": "http://mock-judge:8000/v1/chat/completions",
                "name": "mock-judge-model",
            },
            "scores": [
                {
                    "name": "quality",
                    "rubric": [
                        {"label": "poor", "value": 0},
                        {"label": "good", "value": 1},
                    ],
                }
            ],
        },
        "params": {
            "parallelism": 1,
        },
    }


# Sample dataset rows for FilesetRef tests
FILESET_DATASET_ROWS = [
    {"input": "Explain machine learning", "output": "ML is a subset of AI..."},
    {"input": "What is deep learning?", "output": "Deep learning uses neural networks..."},
    {"input": "Define NLP", "output": "Natural Language Processing is..."},
]


def create_multi_score_llm_judge_job() -> dict:
    """Create an LLM Judge job with multiple scores to verify all are captured."""
    return {
        "dataset": {
            "rows": [
                {"input": "What is Python?", "output": "Python is a programming language."},
                {"input": "Explain AI", "output": "AI stands for Artificial Intelligence."},
            ],
        },
        "metric": {
            "type": "llm-judge",
            "model": {
                "url": "http://mock-judge:8000/v1/chat/completions",
                "name": "mock-judge-model",
            },
            "scores": [
                {
                    "name": "accuracy",
                    "rubric": [
                        {"label": "wrong", "value": 0},
                        {"label": "correct", "value": 1},
                    ],
                },
                {
                    "name": "completeness",
                    "rubric": [
                        {"label": "incomplete", "value": 0},
                        {"label": "partial", "value": 0.5},
                        {"label": "complete", "value": 1},
                    ],
                },
                {
                    "name": "clarity",
                    "rubric": [
                        {"label": "unclear", "value": 0},
                        {"label": "clear", "value": 1},
                    ],
                },
            ],
        },
        "params": {
            "parallelism": 1,
        },
    }


def create_string_check_job() -> dict:
    """Create a string-check metric job for testing non-LLM metrics."""
    return {
        "dataset": {
            "rows": [
                {"text": "Hello World", "expected_prefix": "Hello"},
                {"text": "Goodbye World", "expected_prefix": "Good"},
                {"text": "Python is great", "expected_prefix": "Python"},
            ],
        },
        "metric": {
            "type": "string-check",
            "left_template": "{{text}}",
            "right_template": "{{expected_prefix}}",
            "operation": "startswith",
        },
        "params": {
            "parallelism": 1,
        },
    }


def create_job_with_invalid_template() -> dict:
    """Create a job with invalid Jinja template to test error handling."""
    return {
        "model": {
            "name": "test-model",
            "url": "http://mock-model:8000/v1/chat/completions",
            "format": "nim",
        },
        "dataset": {
            "rows": [
                {"input": "test"},
            ],
        },
        # Invalid template - references undefined variable
        "prompt_template": {"messages": [{"role": "user", "content": "{{undefined_variable}}"}]},
        "metric": {
            "type": "exact-match",
            "reference": "test",
        },
        "params": {
            "parallelism": 1,
        },
    }


def create_online_job_with_inference_params() -> dict:
    """Create an online job with custom inference parameters."""
    return {
        "model": {
            "name": "test-model",
            "url": "http://mock-model:8000/v1/chat/completions",
            "format": "nim",
        },
        "dataset": {
            "rows": [
                {"input": "Hello", "expected": "Hi"},
                {"input": "Goodbye", "expected": "Bye"},
            ],
        },
        "prompt_template": {"messages": [{"role": "user", "content": "{{input}}"}]},
        "metric": {
            "type": "exact-match",
            "reference": "{{item.expected}}",
        },
        "params": {
            "parallelism": 1,
            "max_retries": 2,
            "inference": {
                "temperature": 0.7,
                "max_tokens": 100,
                "top_p": 0.9,
            },
        },
    }


def create_high_parallelism_job() -> dict:
    """Create a job with parallelism > 1 to test concurrent processing."""
    return {
        "dataset": {
            "rows": [
                {"input": f"Question {i}", "output": f"Answer {i}"}
                for i in range(10)  # 10 rows to process in parallel
            ],
        },
        "metric": {
            "type": "llm-judge",
            "model": {
                "url": "http://mock-judge:8000/v1/chat/completions",
                "name": "mock-judge-model",
            },
            "scores": [
                {
                    "name": "score",
                    "rubric": [
                        {"label": "bad", "value": 0},
                        {"label": "good", "value": 1},
                    ],
                }
            ],
        },
        "params": {
            "parallelism": 4,  # Process 4 items concurrently
        },
    }


# =============================================================================
# Integration Tests - evaluate_metric
# =============================================================================


@pytest.mark.integration
class TestEvaluateMetricIntegration:
    """Integration tests for the evaluate_metric task."""

    @pytest.mark.asyncio
    async def test_evaluate_metric_offline_llm_judge(
        self,
        temp_dir: Path,
    ):
        """Test offline LLM Judge metric evaluation with mocked inference."""
        job_config = create_offline_llm_judge_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"length": "short"}'}}]})

        result = await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Verify aggregated result
        assert result is not None
        assert len(result.scores) > 0

        # Verify artifacts were written
        assert (temp_dir / "job.json").exists()
        assert (temp_dir / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).exists()
        assert (temp_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME).exists()

    @pytest.mark.asyncio
    async def test_evaluate_metric_writes_correct_job_json(
        self,
        temp_dir: Path,
    ):
        """Test that job.json contains correct job configuration."""
        job_config = create_offline_llm_judge_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"length": "short"}'}}]})

        await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Verify job.json content
        with open(temp_dir / "job.json") as f:
            saved_job = json.load(f)

        assert saved_job["metric"]["type"] == "llm-judge"
        assert len(saved_job["dataset"]["rows"]) == 2

    @pytest.mark.asyncio
    async def test_evaluate_metric_writes_detailed_results(
        self,
        temp_dir: Path,
    ):
        """Test that results.jsonl contains row-level evaluation details."""
        job_config = create_offline_llm_judge_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"length": "short"}'}}]})

        await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Verify detailed results (JSONL format)
        detailed_path = temp_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()

        # Should have one line per input row
        assert len(lines) == 2

        for line in lines:
            row = json.loads(line)
            assert "item" in row
            assert "metrics" in row

    @pytest.mark.asyncio
    async def test_evaluate_metric_aggregated_scores(
        self,
        temp_dir: Path,
    ):
        """Test that evaluation_results.json contains aggregated scores."""
        job_config = create_offline_llm_judge_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"length": "short"}'}}]})

        await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Verify aggregated results
        with open(temp_dir / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME) as f:
            results = json.load(f)

        assert "scores" in results
        assert len(results["scores"]) > 0

    @pytest.mark.asyncio
    async def test_evaluate_metric_online_with_model_inference(
        self,
        temp_dir: Path,
    ):
        """Test online evaluation that runs model inference then evaluates."""
        job_config = create_online_exact_match_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference_with_side_effects(
            [
                {"choices": [{"message": {"content": "2"}}]},  # Correct
                {"choices": [{"message": {"content": "5"}}]},  # Wrong
            ]
        )

        result = await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Verify we got results
        assert result is not None
        assert len(result.scores) > 0

        # exact-match should have some correct and some wrong
        exact_match_score = next(
            (s for s in result.scores if "exact" in s.name.lower()),
            None,
        )
        assert exact_match_score is not None

    @pytest.mark.asyncio
    async def test_evaluate_metric_with_inference_failure_ignored(
        self,
        temp_dir: Path,
    ):
        """Test that inference failures return NaN when ignored."""
        job_config = create_online_exact_match_job()
        job_config["params"]["ignore_request_failure"] = True
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_failing_inference(Exception("Model unavailable"))

        result = await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Should complete with NaN scores
        assert result is not None
        # All samples failed, so count should be 0 and nan_count should be 2
        for score in result.scores:
            assert score.nan_count == 2
            assert score.count == 0

    @pytest.mark.asyncio
    async def test_evaluate_metric_with_inference_failure_raises(
        self,
        temp_dir: Path,
    ):
        """Test that inference failures raise exception by default."""
        job_config = create_online_exact_match_job()
        # ignore_request_failure defaults to False
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_failing_inference(Exception("Model unavailable"))

        with pytest.raises(EvaluationError, match="sample generation") as exc_info:
            await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)
        assert exc_info.value.index == 0
        assert exc_info.value.phase is EvaluationPhase.SAMPLE_GENERATION

    @pytest.mark.asyncio
    async def test_evaluate_metric_multiple_scores_all_captured(
        self,
        temp_dir: Path,
    ):
        """Test that all scores from multi-score LLM Judge are captured."""
        job_config = create_multi_score_llm_judge_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference(
            {
                "choices": [
                    {"message": {"content": '{"accuracy": "correct", "completeness": "complete", "clarity": "clear"}'}}
                ]
            }
        )

        result = await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Verify all 3 scores are present
        assert result is not None
        assert len(result.scores) == 3

        score_names = {s.name for s in result.scores}
        assert "accuracy" in score_names
        assert "completeness" in score_names
        assert "clarity" in score_names

        # Verify aggregated values are correct (both samples got 1.0)
        for score in result.scores:
            assert score.mean == 1.0
            assert score.count == 2

    @pytest.mark.asyncio
    async def test_evaluate_metric_string_check(
        self,
        temp_dir: Path,
    ):
        """Test string-check metric type (non-LLM metric)."""
        job_config = create_string_check_job()
        job = MetricJobAdapter.validate_python(job_config)

        # String-check doesn't need inference mocking - it's pure computation
        result = await evaluate_metric(job, str(temp_dir))

        # Verify we got results
        assert result is not None
        assert len(result.scores) > 0

        # All 3 rows should pass the "startswith" check
        string_check_score = result.scores[0]
        assert string_check_score.mean == 1.0
        assert string_check_score.count == 3

    @pytest.mark.asyncio
    async def test_evaluate_metric_parallelism_processes_all_rows(
        self,
        temp_dir: Path,
    ):
        """Test that parallelism > 1 processes all rows correctly."""
        job_config = create_high_parallelism_job()
        job = MetricJobAdapter.validate_python(job_config)

        call_count = 0
        row_eval_call_count = 0

        async def counting_inference(
            model: Model,
            request: dict,
            max_retries: int | None,
            **kwargs,
        ) -> dict:
            nonlocal call_count, row_eval_call_count
            call_count += 1
            # LLM judge preflight adds probe calls; count only actual row-eval calls here.
            extra_body = request.get("extra_body", {})
            guided_json = extra_body.get("guided_json") or extra_body.get("nvext", {}).get("guided_json")
            is_preflight = "__nmp_probe_score" in str(guided_json) if guided_json is not None else False
            if not is_preflight:
                row_eval_call_count += 1
            return {"choices": [{"message": {"content": '{"score": "good"}'}}]}

        result = await evaluate_metric(job, str(temp_dir), inference_fn=counting_inference)

        # Verify all 10 rows were processed (exclude preflight probe requests)
        assert row_eval_call_count == 10
        assert call_count >= 10

        # Verify aggregated result has all samples
        assert result is not None
        assert result.scores[0].count == 10

        # Verify detailed results has 10 lines
        detailed_path = temp_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 10

    @pytest.mark.asyncio
    async def test_evaluate_metric_template_error_raises(
        self,
        temp_dir: Path,
    ):
        """Test that Jinja template errors keep strict metric row context."""
        job_config = create_job_with_invalid_template()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": "test"}}]})

        with pytest.raises(EvaluationError, match="sample generation") as exc_info:
            await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)
        assert exc_info.value.index == 0
        assert exc_info.value.phase is EvaluationPhase.SAMPLE_GENERATION

    @pytest.mark.asyncio
    async def test_evaluate_metric_online_with_custom_inference_params(
        self,
        temp_dir: Path,
    ):
        """Test that custom inference params are passed to the model."""
        job_config = create_online_job_with_inference_params()
        job = MetricJobAdapter.validate_python(job_config)

        captured_requests: list[dict] = []

        async def capturing_inference(model: Model, request: dict, max_retries: int | None, **kwargs) -> dict:
            captured_requests.append(request)
            return {"choices": [{"message": {"content": "Hi"}}]}

        await evaluate_metric(job, str(temp_dir), inference_fn=capturing_inference)

        # Verify inference params were included in requests
        assert len(captured_requests) == 2
        for request in captured_requests:
            assert request.get("temperature") == 0.7
            assert request.get("max_tokens") == 100
            assert request.get("top_p") == 0.9

    @pytest.mark.asyncio
    async def test_evaluate_metric_attaches_platform_headers_to_judge_model(
        self,
        temp_dir: Path,
        mocker: MockerFixture,
    ):
        """Judge-model platform headers should be attached to the runtime metric model."""
        job_config = create_offline_llm_judge_job()
        job_config["metric"]["model"]["url"] = "http://nemo-platform-api.default.svc.cluster.local/v1/chat/completions"
        job = MetricJobAdapter.validate_python(job_config)
        captured_model_headers: list[dict[str, str] | None] = []

        async def capturing_inference(
            model: Model,
            request: dict,
            max_retries: int | None,
            **kwargs,
        ) -> dict:
            captured_model_headers.append(model.default_headers)
            return {"choices": [{"message": {"content": '{"length": "short"}'}}]}

        mocker.patch(
            "nmp.evaluator.app.metrics.metric.app_inference.get_platform_headers",
            return_value={"X-NMP-Principal-Id": "service:evaluator"},
        )

        await evaluate_metric(job, str(temp_dir), inference_fn=capturing_inference)

        assert captured_model_headers
        assert captured_model_headers == [{"X-NMP-Principal-Id": "service:evaluator"}] * len(captured_model_headers)

    @pytest.mark.asyncio
    async def test_evaluate_metric_all_nan_scores_detected(
        self,
        temp_dir: Path,
    ):
        """Test that all-NaN scores are properly tracked in aggregation."""
        job_config = create_online_exact_match_job()
        job_config["params"]["ignore_request_failure"] = True
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_failing_inference(Exception("Model unavailable"))

        result = await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # All scores should be NaN
        assert result is not None
        for score in result.scores:
            assert score.count == 0
            assert score.nan_count == 2

        # Verify aggregated results file reflects NaN state
        with open(temp_dir / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME) as f:
            results = json.load(f)

        for score in results["scores"]:
            assert score["count"] == 0
            assert score["nan_count"] == 2


@pytest.mark.integration
class TestEvaluateMetricWithFilesetRef:
    """Integration tests for evaluate_metric with FilesetRef datasets.

    These tests verify that the evaluate_metric task can load datasets
    from downloaded files (simulating the download_fileset step).
    """

    @pytest.mark.asyncio
    async def test_evaluate_metric_with_fileset_urn_dataset(
        self,
        temp_dir: Path,
    ):
        """Test evaluation with FilesetRef dataset loads from downloaded file."""
        # Create a "downloaded" dataset directory with dataset.json
        # The dataset-download step places files at {dataset_dir}/{workspace}/{fileset-name}/
        fileset_ref = f"{TEST_WORKSPACE}/test-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        fileset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Write dataset.json (simulating what download_fileset would produce)
        dataset_file = fileset_dir / INLINE_DATASET_FILENAME
        with open(dataset_file, "w") as f:
            json.dump(FILESET_DATASET_ROWS, f)

        # Create job with FilesetRef
        job_config = create_fileset_urn_llm_judge_job(fileset_ref)
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"quality": "good"}'}}]})

        result = await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir), inference_fn=mock_inference)

        # Verify we got results for all 3 rows
        assert result is not None
        assert len(result.scores) > 0

        # Verify detailed results were written
        detailed_path = results_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 3  # One line per dataset row

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_urn_missing_file_raises(
        self,
        temp_dir: Path,
    ):
        """Test that FilesetRef without downloaded file raises clear error."""
        # Create empty dataset directory (no fileset directory)
        dataset_dir = temp_dir / "datasets"
        dataset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Create job with FilesetRef
        job_config = create_fileset_urn_llm_judge_job(f"{TEST_WORKSPACE}/missing-fileset")
        job = MetricJobAdapter.validate_python(job_config)

        with pytest.raises(ValueError, match="Failed to load dataset"):
            await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir))

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_urn_empty_dataset_raises(
        self,
        temp_dir: Path,
    ):
        """Test that empty downloaded dataset raises clear error."""
        # Create dataset directory with empty dataset.json
        # The dataset-download step places files at {dataset_dir}/{workspace}/{fileset-name}/
        fileset_ref = f"{TEST_WORKSPACE}/empty-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        fileset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Write empty dataset.json
        dataset_file = fileset_dir / INLINE_DATASET_FILENAME
        with open(dataset_file, "w") as f:
            json.dump([], f)

        # Create job with FilesetRef
        job_config = create_fileset_urn_llm_judge_job(fileset_ref)
        job = MetricJobAdapter.validate_python(job_config)

        with pytest.raises(ValueError, match="empty"):
            await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir))

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_urn_respects_limit_samples(
        self,
        temp_dir: Path,
    ):
        """Test that limit_samples parameter works with FilesetRef datasets."""
        # Create dataset with 3 rows
        # The dataset-download step places files at {dataset_dir}/{workspace}/{fileset-name}/
        fileset_ref = f"{TEST_WORKSPACE}/test-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        fileset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        dataset_file = fileset_dir / INLINE_DATASET_FILENAME
        with open(dataset_file, "w") as f:
            json.dump(FILESET_DATASET_ROWS, f)

        # Create job with limit_samples=2
        job_config = create_fileset_urn_llm_judge_job(fileset_ref)
        job_config["params"]["limit_samples"] = 2
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"quality": "good"}'}}]})

        await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir), inference_fn=mock_inference)

        # Verify only 2 rows were processed
        detailed_path = results_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 2  # Limited to 2 samples

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_with_fragment_specific_file(
        self,
        temp_dir: Path,
    ):
        """Test loading a specific file via fragment (workspace/fileset#file.json)."""
        # Create dataset directory with multiple files
        fileset_ref = f"{TEST_WORKSPACE}/multi-file-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        fileset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Write multiple dataset files
        train_data = [{"input": "train1", "output": "resp1"}, {"input": "train2", "output": "resp2"}]
        test_data = [{"input": "test1", "output": "resp1"}]

        with open(fileset_dir / "train.json", "w") as f:
            json.dump(train_data, f)
        with open(fileset_dir / "test.json", "w") as f:
            json.dump(test_data, f)

        # Create job referencing specific file via fragment
        job_config = create_fileset_urn_llm_judge_job(f"{fileset_ref}#train.json")
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"quality": "good"}'}}]})

        await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir), inference_fn=mock_inference)

        # Verify only train.json rows were processed (2 rows)
        detailed_path = results_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_with_glob_pattern(
        self,
        temp_dir: Path,
    ):
        """Test loading files matching a glob pattern (workspace/fileset#*.jsonl)."""
        # Create dataset directory with multiple file types
        fileset_ref = f"{TEST_WORKSPACE}/glob-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        fileset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Write JSONL files (should match *.jsonl)
        jsonl_data = [
            {"input": "jsonl1", "output": "resp1"},
            {"input": "jsonl2", "output": "resp2"},
        ]
        with open(fileset_dir / "data.jsonl", "w") as f:
            for row in jsonl_data:
                f.write(json.dumps(row) + "\n")

        # Write JSON file (should not match *.jsonl)
        json_data = [{"input": "json1", "output": "resp1"}]
        with open(fileset_dir / "other.json", "w") as f:
            json.dump(json_data, f)

        # Create job with glob pattern
        job_config = create_fileset_urn_llm_judge_job(f"{fileset_ref}#*.jsonl")
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"quality": "good"}'}}]})

        await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir), inference_fn=mock_inference)

        # Verify only JSONL rows were processed (2 rows)
        detailed_path = results_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_loads_all_files_when_no_fragment(
        self,
        temp_dir: Path,
    ):
        """Test that all parsable files are loaded when no fragment is specified."""
        # Create dataset directory with multiple files
        fileset_ref = f"{TEST_WORKSPACE}/all-files-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        fileset_dir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Write multiple dataset files in different formats
        json_data = [{"input": "json1", "output": "resp1"}]
        jsonl_data = [{"input": "jsonl1", "output": "resp1"}]

        with open(fileset_dir / "data.json", "w") as f:
            json.dump(json_data, f)
        with open(fileset_dir / "train.jsonl", "w") as f:
            for row in jsonl_data:
                f.write(json.dumps(row) + "\n")
        # Also add a non-data file that should be skipped
        (fileset_dir / "README.md").write_text("# This should be skipped")

        # Create job without fragment (should load all parsable files)
        job_config = create_fileset_urn_llm_judge_job(fileset_ref)
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"quality": "good"}'}}]})

        await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir), inference_fn=mock_inference)

        # Verify all data rows from both files were processed (1 + 1 = 2 rows)
        detailed_path = results_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_evaluate_metric_fileset_with_subdirectory_path(
        self,
        temp_dir: Path,
    ):
        """Test loading a file from a subdirectory via fragment."""
        # Create dataset directory with nested structure
        fileset_ref = f"{TEST_WORKSPACE}/nested-fileset"
        dataset_dir = temp_dir / "datasets"
        fileset_dir = dataset_dir / fileset_ref
        subdir = fileset_dir / "data" / "train"
        subdir.mkdir(parents=True)
        results_dir = temp_dir / "results"
        results_dir.mkdir(parents=True)

        # Write dataset in subdirectory
        train_data = [{"input": "nested1", "output": "resp1"}, {"input": "nested2", "output": "resp2"}]
        with open(subdir / "dataset.json", "w") as f:
            json.dump(train_data, f)

        # Create job referencing file in subdirectory
        job_config = create_fileset_urn_llm_judge_job(f"{fileset_ref}#data/train/dataset.json")
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"quality": "good"}'}}]})

        await evaluate_metric(job, str(results_dir), dataset_dir=str(dataset_dir), inference_fn=mock_inference)

        # Verify nested file was loaded (2 rows)
        detailed_path = results_dir / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME
        with open(detailed_path) as f:
            lines = f.readlines()
        assert len(lines) == 2


@pytest.mark.integration
class TestEvaluateMetricWithResultsUpload:
    """Integration tests for evaluate_metric + handle_results flow."""

    @pytest.mark.asyncio
    async def test_evaluate_then_upload_results(
        self,
        sdk: NeMoPlatform,
        async_sdk_with_jobs,
        job_context,
        temp_dir: Path,
    ):
        """Test the full flow: evaluate metric -> upload results to Jobs API."""
        job_name = "test-eval-upload-job"

        # Create job using job_context for proper cleanup
        job_context.create(job_name)

        # Run evaluation
        job_config = create_offline_llm_judge_job()
        job = MetricJobAdapter.validate_python(job_config)

        mock_inference = make_mock_inference({"choices": [{"message": {"content": '{"length": "short"}'}}]})

        await evaluate_metric(job, str(temp_dir), inference_fn=mock_inference)

        # Upload results using handle_results_async
        config = ResultsHandlerConfig(
            NEMO_JOB_ID=job_name,
            NEMO_JOB_WORKSPACE=TEST_WORKSPACE,
        )
        await handle_results_async(job, config, str(temp_dir), async_sdk_with_jobs)

        # Verify results were uploaded
        results = sdk.jobs.results.list(name=job_name, workspace=TEST_WORKSPACE)
        result_names = [r.name for r in results.data]

        assert "artifacts" in result_names
        assert "aggregate-scores" in result_names

        # Cleanup
        job_context.cleanup(job_name)


@pytest.mark.integration
class TestEvaluateMetricHelpers:
    def test_json_default_prefers_supported_serializers(self):
        class WithDict:
            def dict(self):
                return {"kind": "dict"}

        class WithModelDump:
            def model_dump(self):
                return {"kind": "model_dump"}

        class WithToDict:
            def to_dict(self):
                return {"kind": "to_dict"}

        class Fallback:
            def __str__(self) -> str:
                return "fallback"

        assert _json_default(WithDict()) == {"kind": "dict"}
        assert _json_default(WithModelDump()) == {"kind": "model_dump"}
        assert _json_default(WithToDict()) == {"kind": "to_dict"}
        assert _json_default(Fallback()) == "fallback"

    def test_no_aggregated_metric_scores_detects_empty_and_nonempty_results(self):
        assert no_aggregated_metric_scores(AggregatedMetricResult(scores=[])) is True

        all_nan_result = AggregatedMetricResult(
            scores=[
                AggregateRangeScore(
                    name="score",
                    count=0,
                    nan_count=2,
                    sum=0.0,
                    mean=None,
                    min=None,
                    max=None,
                    std_dev=None,
                    variance=None,
                )
            ]
        )
        assert no_aggregated_metric_scores(all_nan_result) is True

        valid_result = AggregatedMetricResult(
            scores=[
                AggregateRangeScore(
                    name="score",
                    count=1,
                    nan_count=0,
                    sum=1.0,
                    mean=1.0,
                    min=1.0,
                    max=1.0,
                    std_dev=0.0,
                    variance=0.0,
                )
            ]
        )
        assert no_aggregated_metric_scores(valid_result) is False

    def test_metric_evaluation_entrypoint_helpers(self):
        assert metric_evaluation_entrypoint() == ["python", "-m", "nmp.evaluator.tasks.evaluate_metric"]
        assert metric_evaluation_entrypoint_args() == []
        assert metric_evaluation_entrypoint_args(
            progress_tracking_url="https://callback.test",
            progress_tracking_interval=10,
        ) == [
            "--progress-tracking-url",
            "https://callback.test",
            "--progress-tracking-interval",
            "10",
        ]

    def test_load_dataset_items_rejects_empty_inline_rows(self, mocker: MockerFixture):
        job = mocker.Mock(dataset=DatasetRows.model_construct(rows=[]))

        with pytest.raises(ValueError, match="DatasetRows has no rows"):
            _load_dataset_items(job)

    def test_load_dataset_items_rejects_unsupported_dataset_type(self, mocker: MockerFixture):
        job = mocker.Mock(dataset="unsupported")

        with pytest.raises(ValueError, match="Unsupported dataset type: str"):
            _load_dataset_items(job)

    @pytest.mark.asyncio
    async def test_evaluate_metric_configures_progress_tracking(self, temp_dir: Path, mocker: MockerFixture):
        job_config = create_online_exact_match_job()
        job = MetricJobAdapter.validate_python(job_config)
        progress_tracking = mocker.Mock(total_samples=0, interval=5)
        progress_hook = mocker.Mock()
        progress_hook.postprocess.side_effect = lambda response, id=None: response
        progress_hook_cls = mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.inference_hooks.ProgressTrackingHook",
            return_value=progress_hook,
        )

        await evaluate_metric(
            job,
            str(temp_dir),
            progress_tracking=progress_tracking,
            inference_fn=make_mock_inference({"choices": [{"message": {"content": "2"}}]}),
        )

        assert progress_tracking.total_samples == 2
        progress_hook_cls.assert_called_once_with(progress_tracking)


@pytest.mark.integration
class TestEvaluateMetricTaskWrapper:
    @pytest.mark.asyncio
    async def test_main_marks_progress_complete_when_results_exist(
        self, temp_dir: Path, mocker, monkeypatch: pytest.MonkeyPatch
    ):
        config_file = temp_dir / "job.json"
        config_file.write_text(json.dumps(create_offline_llm_judge_job()))
        monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_file))
        monkeypatch.setenv(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, str(temp_dir))
        progress_tracking = mocker.Mock()
        progress_tracking.update_progress = mocker.Mock()
        progress_tracking.stop = mocker.Mock()
        mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.initialize_logging")
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.ProgressTracking",
            return_value=progress_tracking,
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.evaluate_metric",
            new_callable=mocker.AsyncMock,
            return_value=AggregatedMetricResult(
                scores=[
                    AggregateRangeScore(
                        name="score",
                        count=1,
                        nan_count=0,
                        sum=1.0,
                        mean=1.0,
                        min=1.0,
                        max=1.0,
                        std_dev=0.0,
                        variance=0.0,
                    )
                ]
            ),
        )

        result = await main(
            [
                "--progress-tracking-url",
                "https://callback.test",
                "--skip-upload-results",
                "True",
            ]
        )

        assert result == 0
        progress_tracking.update_progress.assert_called_once_with(100)
        progress_tracking.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_raises_when_no_aggregated_scores_exist(
        self, temp_dir: Path, mocker, monkeypatch: pytest.MonkeyPatch
    ):
        config_file = temp_dir / "job.json"
        config_file.write_text(json.dumps(create_offline_llm_judge_job()))
        monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_file))
        monkeypatch.setenv(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, str(temp_dir))
        progress_tracking = mocker.Mock()
        progress_tracking.update_progress = mocker.Mock()
        progress_tracking.stop = mocker.Mock()
        mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.initialize_logging")
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.ProgressTracking",
            return_value=progress_tracking,
        )
        mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.evaluate_metric",
            new_callable=mocker.AsyncMock,
            return_value=AggregatedMetricResult(scores=[]),
        )

        with pytest.raises(ValueError, match="no evaluation results detected"):
            await main(
                [
                    "--progress-tracking-url",
                    "https://callback.test",
                    "--skip-upload-results",
                    "True",
                ]
            )

        progress_tracking.update_progress.assert_not_called()
        progress_tracking.stop.assert_called_once()

    def test_run_returns_main_result(self, mocker):
        register_handlers = mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.register_task_signal_handlers")

        def _run_and_close(coro):
            coro.close()
            return 7

        mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.asyncio.run", side_effect=_run_and_close)

        assert run([]) == 7
        register_handlers.assert_called_once()

    def test_run_returns_zero_on_keyboard_interrupt(self, mocker):
        mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.register_task_signal_handlers")

        def _raise_keyboard_interrupt(coro):
            coro.close()
            raise KeyboardInterrupt

        mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.asyncio.run",
            side_effect=_raise_keyboard_interrupt,
        )
        log_mock = mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.log")

        assert run([]) == 0
        log_mock.info.assert_called_once_with("Received termination signal. Exiting task gracefully.")

    def test_run_returns_one_on_unhandled_exception(self, mocker):
        mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.register_task_signal_handlers")

        def _raise_runtime_error(coro):
            coro.close()
            raise RuntimeError("boom")

        mocker.patch(
            "nmp.evaluator.tasks.evaluate_metric.__main__.asyncio.run",
            side_effect=_raise_runtime_error,
        )
        log_mock = mocker.patch("nmp.evaluator.tasks.evaluate_metric.__main__.log")

        assert run([]) == 1
        log_mock.exception.assert_called_once_with("Error in evaluate_metric task")
