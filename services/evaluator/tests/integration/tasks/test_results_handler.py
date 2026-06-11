# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the metric_results task.

These tests verify that the metric_results task correctly:
- Uploads evaluation results to the Jobs API
- Uploads result artifacts to the Files API
- Parses both EvalFactory and custom result formats
- Handles edge cases (missing files, invalid formats, special characters)

Uses task_harness for in-memory service testing.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.values import MetricScore
from nmp.common.jobs.constants import (
    NEMO_JOB_STEP_CONFIG_FILE_NAME,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.core.files.service import FilesService
from nmp.core.jobs.service import JobsService
from nmp.evaluator.app.jobs.constants import (
    EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME,
    EVALUATION_RESULTS_AGG_SCORES_FILE_NAME,
    EVALUATION_RESULTS_ROW_SCORES_FILE_NAME,
    JOB_RESULTS_AGGREGATE_SCORES,
    JOB_RESULTS_ROW_SCORES,
)
from nmp.evaluator.service import EvaluatorService
from nmp.evaluator.tasks import metric_results
from nmp.testing import task_harness

# Test workspace and job ID
TEST_WORKSPACE = "test-workspace"
TEST_JOB_ID = "test-job-12345"


def task_runtime_env(tmp_path: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build the job runtime env consumed by the metric_results task."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(exist_ok=True)
    results_link = storage_dir / "results"
    if not results_link.exists():
        results_link.symlink_to(tmp_path, target_is_directory=True)
    env = {
        "NEMO_JOB_WORKSPACE": TEST_WORKSPACE,
        "NEMO_JOB_ID": TEST_JOB_ID,
        NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR: f"{tmp_path}/{NEMO_JOB_STEP_CONFIG_FILE_NAME}",
        PERSISTENT_JOB_STORAGE_PATH_ENVVAR: str(storage_dir),
    }
    if extra:
        env.update(extra)
    return env


def create_test_job(sdk, workspace: str, job_id: str):
    """Create a test job for result uploads."""
    # Create a minimal job that the results handler can reference
    sdk.jobs.create(
        workspace=workspace,
        name=job_id,
        source="evaluator",
        spec={},
        platform_spec={
            "steps": [
                {
                    "name": "evaluate",
                    "executor": {
                        "provider": "cpu",
                        "profile": "default",
                        "container": {
                            "image": "test:latest",
                            "entrypoint": ["entrypoint"],
                            "command": ["command"],
                        },
                    },
                }
            ]
        },
    )


def download_json_result(sdk, name: str) -> dict:
    response = sdk.jobs.results.download(name=name, job=TEST_JOB_ID, workspace=TEST_WORKSPACE)
    return json.loads(response.read().decode())


def download_jsonl_result(sdk, name: str) -> list[dict]:
    response = sdk.jobs.results.download(name=name, job=TEST_JOB_ID, workspace=TEST_WORKSPACE)
    return [json.loads(line) for line in response.read().decode().splitlines() if line.strip()]


@pytest.fixture
def metric_job_spec() -> dict:
    return {"metric": {"type": "bleu", "references": []}, "dataset": {"rows": [{"data": "value"}]}}


@pytest.fixture
def retriever_metric_job_spec() -> dict:
    return {
        "metric": {"type": MetricType.SYSTEM_RETRIEVER, "name": "retriever-map"},
        "dataset": {"rows": [{"data": "value"}]},
    }


@pytest.fixture
def benchmark_job_spec() -> dict:
    return {"benchmark": {"name": "some-system-benchmark"}, "dataset": {"rows": [{"data": "value"}]}}


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.integration
class TestMetricResultsTask:
    """Integration tests for the metric_results task."""

    @pytest.mark.asyncio
    async def test_upload_custom_results(self, tmp_path: Path, metric_job_spec):
        """Test uploading custom evaluation results format."""
        # Create results files
        agg_scores = {"scores": [{"name": "accuracy", "mean": 0.85, "count": 100, "nan_count": 0}]}
        metric_ref = f"{TEST_WORKSPACE}/my-acc-metric"
        row_scores = [
            {
                "item": {"row_id": 0},
                "sample": {},
                "metrics": {metric_ref: [{"name": "accuracy", "value": 0.9}]},
                "requests": [],
            },
            {
                "item": {"row_id": 1},
                "sample": {},
                "metrics": {metric_ref: [{"name": "accuracy", "value": 0.8}]},
                "requests": [],
            },
        ]

        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps(agg_scores))
        (tmp_path / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME).write_text(
            "\n".join(json.dumps(row) for row in row_scores)
        )

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            EvaluatorService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            # Setup: Create the job that results will be uploaded to
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            # Run task
            result = ctx.run_task(args=[])

            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

            # Verify results were uploaded to Jobs API
            job_results = ctx.sdk.jobs.results.list(TEST_JOB_ID, workspace=TEST_WORKSPACE)
            result_names = [r.name for r in job_results.data]

            assert JOB_RESULTS_AGGREGATE_SCORES in result_names
            assert JOB_RESULTS_ROW_SCORES in result_names

            # Verify result download serializes
            agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
            assert len(agg_scores_resp["scores"]) == 1
            assert agg_scores_resp["scores"][0]["name"] == "accuracy"

            row_scores = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
            assert len(row_scores) == 2, "unexpected number of row scores"
            for row in row_scores:
                assert len(row["metrics"]) == 1
                assert metric_ref in row["metrics"]

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="EvalFactory format requires YAML with specific schema - covered by separate EvalFactory tests"
    )
    async def test_upload_evalfactory_results(self, tmp_path: Path):
        """Test uploading EvalFactory format results."""
        # EvalFactory uses a complex YAML format with tasks/groups structure
        # This is covered by dedicated EvalFactory integration tests
        pass

    @pytest.mark.asyncio
    async def test_missing_results_directory(self, tmp_path: Path, metric_job_spec):
        """Test handling of non-existent results directory."""
        nonexistent_dir = tmp_path / "nonexistent"
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            config={},
            env={
                "NEMO_JOB_WORKSPACE": TEST_WORKSPACE,
                "NEMO_JOB_ID": TEST_JOB_ID,
                NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR: f"{tmp_path}/{NEMO_JOB_STEP_CONFIG_FILE_NAME}",
                PERSISTENT_JOB_STORAGE_PATH_ENVVAR: str(nonexistent_dir),
            },
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            # Task should fail gracefully
            assert result.exit_code != 0
            assert "FileNotFoundError" in result.stderr

    @pytest.mark.asyncio
    async def test_empty_results_directory(self, tmp_path: Path, metric_job_spec):
        """Test handling of empty results directory (no result files)."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            # Should complete but may warn about missing files
            # The behavior depends on implementation - just verify it doesn't crash
            assert result.exit_code in (0, 1)
            assert "No custom evaluation results file 'aggregate-scores.json' found" in result.stderr

    @pytest.mark.asyncio
    async def test_custom_takes_priority_over_evalfactory(self, tmp_path: Path, metric_job_spec):
        """Test that custom parser is used by default when no harness env is set."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))

        # Create custom results (these should take priority)
        custom_scores = {"scores": [{"name": "accuracy", "mean": 0.9, "count": 100, "nan_count": 0}]}
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps(custom_scores))

        # Create a dummy EvalFactory file (would fail parsing if actually used)
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("not valid yaml")

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            EvaluatorService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            # Should pass because custom format takes priority
            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

            # Verify the custom scores were uploaded (not EvalFactory)
            job_results = ctx.sdk.jobs.results.list(TEST_JOB_ID, workspace=TEST_WORKSPACE)
            agg_result = next((r for r in job_results.data if r.name == JOB_RESULTS_AGGREGATE_SCORES), None)
            assert agg_result is not None

            # Verify result download serializes
            agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
            assert len(agg_scores_resp["scores"]) == 1
            assert agg_scores_resp["scores"][0]["name"] == "accuracy"

            # No row results uploaded
            row_scores_resp = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
            assert len(row_scores_resp) == 0

    @pytest.mark.asyncio
    async def test_unknown_eval_harness_fails_fast(self, tmp_path: Path, metric_job_spec):
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps({"scores": {}}))

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            config={},
            env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "unknown_harness"}),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)
            result = ctx.run_task(args=[])
            assert result.exit_code != 0
            assert "Unsupported eval harness 'unknown_harness'" in result.stderr

    @pytest.mark.asyncio
    async def test_preserves_stats_metadata(self, tmp_path: Path, metric_job_spec):
        """Test that full stats metadata is preserved in results."""
        agg_scores = {
            "scores": [
                {
                    "name": "f1_score",
                    "mean": 0.78,
                    "count": 50,
                    "nan_count": 0,
                    "min": 0.2,
                    "max": 1.0,
                    "sum": 39.0,
                }
            ],
        }

        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps(agg_scores))

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            EvaluatorService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

            agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
            assert len(agg_scores_resp["scores"]) == 1
            score = agg_scores_resp["scores"][0]
            assert score["name"] == "f1_score"
            assert score["mean"] == 0.78
            assert score["count"] == 50
            assert score["min"] == 0.2
            assert score["max"] == 1.0
            assert score["sum"] == 39.0
            assert score.get("std_dev") is None

    @pytest.mark.asyncio
    async def test_special_characters_in_score_names(self, tmp_path: Path, metric_job_spec):
        """Test handling of special characters in metric/score names."""
        agg_scores = {
            "scores": [
                {"name": "metric-with-dashes", "mean": 0.5, "count": 100, "nan_count": 0},
                {"name": "metric_with_underscores", "mean": 0.6, "count": 100, "nan_count": 0},
                {"name": "metric.with.dots", "mean": 0.7, "count": 100, "nan_count": 0},
            ],
        }
        expected_score_names = [
            "metric-with-dashes",
            "metric_with_underscores",
            "metric.with.dots",
        ]

        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps(agg_scores))

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            EvaluatorService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

            agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
            assert len(agg_scores_resp["scores"]) == 3
            assert [score["name"] for score in agg_scores_resp["scores"]] == expected_score_names

    @pytest.mark.asyncio
    async def test_multiple_scores_uploaded(self, tmp_path: Path, metric_job_spec):
        """Test that multiple scores are all uploaded correctly."""
        agg_scores = {
            "scores": [
                {"name": "accuracy", "mean": 0.85, "count": 5, "nan_count": 0},
                {"name": "precision", "mean": 0.80, "count": 5, "nan_count": 0},
                {"name": "recall", "mean": 0.75, "count": 5, "nan_count": 0},
                {"name": "f1", "mean": 0.77, "count": 5, "nan_count": 0},
            ],
        }
        expected_score_names = ["accuracy", "precision", "recall", "f1"]

        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps(agg_scores))

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            EvaluatorService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

            # Verify results exist
            job_results = ctx.sdk.jobs.results.list(TEST_JOB_ID, workspace=TEST_WORKSPACE)
            assert len(job_results.data) > 0

            agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
            assert len(agg_scores_resp["scores"]) == 4
            assert [score["name"] for score in agg_scores_resp["scores"]] == expected_score_names

    @pytest.mark.asyncio
    async def test_evalfactory_parser_creates_empty_row_scores(self, tmp_path: Path, benchmark_job_spec):
        """EvalFactory parser should normalize to aggregate+row artifacts even without row data."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(benchmark_job_spec))
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("tasks: {}")

        with patch(
            "nmp.evaluator.app.jobs.result_parsers.evalfactory._parse_evalfactory_scores",
            return_value=[MetricScore(name="accuracy", value=1.0)],
        ):
            async with task_harness(
                metric_results,
                FilesService,
                JobsService,
                EvaluatorService,
                config={},
                env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "simple_evals"}),
            ) as ctx:
                create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

                result = ctx.run_task(args=[])
                assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

                job_results = ctx.sdk.jobs.results.list(TEST_JOB_ID, workspace=TEST_WORKSPACE)
                result_names = [r.name for r in job_results.data]
                assert JOB_RESULTS_AGGREGATE_SCORES in result_names
                assert JOB_RESULTS_ROW_SCORES in result_names

                agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
                assert len(agg_scores_resp["results"]) == 1
                assert len(agg_scores_resp["results"][0]["scores"]) == 1

                row_scores_resp = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
                assert len(row_scores_resp) == 0

    @pytest.mark.asyncio
    async def test_evalfactory_parser_parses_retriever_rows(self, tmp_path: Path, retriever_metric_job_spec):
        """EvalFactory parser should convert retriever_cached_outputs.json into row-scores.jsonl."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(retriever_metric_job_spec))
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("tasks: {}")
        retriever_rows = tmp_path / "results" / "retriever_cached_outputs.json"
        retriever_rows.parent.mkdir(parents=True, exist_ok=True)
        retriever_rows.write_text(
            json.dumps(
                {
                    "q1": {"retrieved_docs": [{"doc_id": "d1", "score": 0.11}]},
                    "q2": {"retrieved_docs": [{"doc_id": "d2", "score": 0.22}]},
                }
            )
        )

        with patch(
            "nmp.evaluator.app.jobs.result_parsers.evalfactory._parse_evalfactory_scores",
            return_value=[MetricScore(name="accuracy", value=1.0)],
        ):
            async with task_harness(
                metric_results,
                FilesService,
                JobsService,
                EvaluatorService,
                config={},
                env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "retriever"}),
            ) as ctx:
                create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

                result = ctx.run_task(args=[])
                assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

                # Expected RowScores
                # RowScore(item={'query_id': 'q1'}, metrics={}, requests=[], sample={}, retriever={'retrieved_docs': [{'doc_id': 'd1', 'score': 0.11}]})
                # RowScore(item={'query_id': 'q2'}, metrics={}, requests=[], sample={}, retriever={'retrieved_docs': [{'doc_id': 'd2', 'score': 0.22}]})

                parsed = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
                assert len(parsed) == 2
                assert {row["item"]["query_id"] for row in parsed} == {"q1", "q2"}
                assert all(row["row_index"] is None for row in parsed)
                assert all(row["metric_errors"] is None for row in parsed)
                assert all("error" not in row for row in parsed)
                assert [row["retriever"] for row in parsed] == [
                    {"retrieved_docs": [{"doc_id": "d1", "score": 0.11}]},
                    {"retrieved_docs": [{"doc_id": "d2", "score": 0.22}]},
                ]

    @pytest.mark.asyncio
    async def test_evalfactory_parser_fails_on_invalid_retriever_rows(self, tmp_path: Path, retriever_metric_job_spec):
        """EvalFactory parser should hard-fail when retriever row artifact is malformed."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(retriever_metric_job_spec))
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("tasks: {}")
        retriever_rows = tmp_path / "results" / "retriever_cached_outputs.json"
        retriever_rows.parent.mkdir(parents=True, exist_ok=True)
        retriever_rows.write_text(json.dumps({"q1": "invalid"}))

        with patch(
            "nmp.evaluator.app.jobs.result_parsers.evalfactory._parse_evalfactory_scores",
            return_value=[MetricScore(name="accuracy", value=1.0)],
        ):
            async with task_harness(
                metric_results,
                FilesService,
                JobsService,
                config={},
                env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "retriever"}),
            ) as ctx:
                create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

                result = ctx.run_task(args=[])
                assert result.exit_code != 0
                assert "Invalid EvalFactory retriever row artifact entry" in result.stderr

    @pytest.mark.asyncio
    async def test_evalfactory_parser_parses_cached_outputs_jsonl(self, tmp_path: Path, benchmark_job_spec):
        """EvalFactory parser should convert cached-output jsonl rows to row-scores.jsonl."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(benchmark_job_spec))
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("tasks: {}")
        cached_rows = tmp_path / "results" / "answer_acc.jsonl"
        cached_rows.parent.mkdir(parents=True, exist_ok=True)
        cached_rows.write_text("\n".join([json.dumps({"question": "q1"}), json.dumps({"question": "q2"})]))

        with patch(
            "nmp.evaluator.app.jobs.result_parsers.evalfactory._parse_evalfactory_scores",
            return_value=[MetricScore(name="accuracy", value=1.0)],
        ):
            async with task_harness(
                metric_results,
                FilesService,
                JobsService,
                EvaluatorService,
                config={},
                env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "simple_evals"}),
            ) as ctx:
                create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

                result = ctx.run_task(args=[])
                assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

                agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
                assert len(agg_scores_resp["results"]) == 1
                assert len(agg_scores_resp["results"][0]["scores"]) == 1

                parsed = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
                assert len(parsed) == 2
                assert parsed[0]["item"]["question"] == "q1"
                assert parsed[1]["item"]["question"] == "q2"
                assert all(row["row_index"] is None for row in parsed)
                assert all(row["metric_errors"] is None for row in parsed)
                assert all("error" not in row for row in parsed)

    @pytest.mark.asyncio
    async def test_evalfactory_agentic_uses_harness_cached_output_detection(self, tmp_path: Path):
        """Agentic parser should resolve row source from harness-specific cached-output files."""
        job_spec = {
            "metric": {"type": MetricType.SYSTEM, "name": "trajectory-evaluation"},
            "dataset": {"rows": [{"data": "value"}]},
        }
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(job_spec))
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("tasks: {}")
        rows_dir = tmp_path / "results"
        rows_dir.mkdir(parents=True, exist_ok=True)
        (rows_dir / "trajectory_eval_input.jsonl").write_text(json.dumps({"question": "from-config"}) + "\n")
        (rows_dir / "other.jsonl").write_text(json.dumps({"question": "not-selected"}) + "\n")

        with patch(
            "nmp.evaluator.app.jobs.result_parsers.evalfactory._parse_evalfactory_scores",
            return_value=[MetricScore(name="accuracy", value=1.0)],
        ):
            async with task_harness(
                metric_results,
                FilesService,
                JobsService,
                EvaluatorService,
                config={},
                env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "agentic_eval"}),
            ) as ctx:
                create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

                result = ctx.run_task(args=[])
                assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

                parsed = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
                assert len(parsed) == 1
                parsed = parsed[0]
                assert parsed["item"]["question"] == "from-config"

    @pytest.mark.asyncio
    async def test_evalfactory_parser_fails_on_invalid_cached_outputs_jsonl(self, tmp_path: Path, benchmark_job_spec):
        """EvalFactory parser should hard-fail when cached-output jsonl contains non-object rows."""
        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(benchmark_job_spec))
        (tmp_path / EVALFACTORY_EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text("tasks: {}")
        cached_rows = tmp_path / "results" / "answer_acc.jsonl"
        cached_rows.parent.mkdir(parents=True, exist_ok=True)
        cached_rows.write_text(json.dumps(["invalid"]))

        with patch(
            "nmp.evaluator.app.jobs.result_parsers.evalfactory._parse_evalfactory_scores",
            return_value=[MetricScore(name="accuracy", value=1.0)],
        ):
            async with task_harness(
                metric_results,
                FilesService,
                JobsService,
                config={},
                env=task_runtime_env(tmp_path, {"NEMO_EVAL_HARNESS": "simple_evals"}),
            ) as ctx:
                create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

                result = ctx.run_task(args=[])
                assert result.exit_code != 0
                assert "Invalid EvalFactory cached-outputs row" in result.stderr

    @pytest.mark.asyncio
    async def test_large_row_scores_file(self, tmp_path: Path, metric_job_spec):
        """Test handling of large row scores file."""
        agg_scores = {"scores": [{"name": "accuracy", "mean": 0.85, "count": 1000, "nan_count": 0}]}
        row_scores = [
            {
                "item": {"row_id": i},
                "sample": {},
                "metrics": {"score": [{"name": "score", "value": 0.8 + (i % 20) / 100}]},
                "requests": [],
            }
            for i in range(1000)
        ]

        (tmp_path / NEMO_JOB_STEP_CONFIG_FILE_NAME).write_text(json.dumps(metric_job_spec))
        (tmp_path / EVALUATION_RESULTS_AGG_SCORES_FILE_NAME).write_text(json.dumps(agg_scores))
        (tmp_path / EVALUATION_RESULTS_ROW_SCORES_FILE_NAME).write_text(
            "\n".join(json.dumps(row) for row in row_scores)
        )

        async with task_harness(
            metric_results,
            FilesService,
            JobsService,
            EvaluatorService,
            config={},
            env=task_runtime_env(tmp_path),
        ) as ctx:
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"

            agg_scores_resp = download_json_result(ctx.sdk, JOB_RESULTS_AGGREGATE_SCORES)
            assert len(agg_scores_resp["scores"]) == 1
            assert agg_scores_resp["scores"][0]["count"] == 1000

            row_scores = download_jsonl_result(ctx.sdk, JOB_RESULTS_ROW_SCORES)
            assert len(row_scores) == 1000, "unexpected number of row scores"
