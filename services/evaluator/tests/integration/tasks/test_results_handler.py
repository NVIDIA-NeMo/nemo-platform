# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the metric_results task."""

import json
from pathlib import Path

import pytest
from nmp.common.jobs.constants import (
    NEMO_JOB_STEP_CONFIG_FILE_NAME,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.core.files.service import FilesService
from nmp.core.jobs.service import JobsService
from nmp.evaluator.app.jobs.constants import (
    EVALUATION_RESULTS_AGG_SCORES_FILE_NAME,
    EVALUATION_RESULTS_ROW_SCORES_FILE_NAME,
    JOB_RESULTS_AGGREGATE_SCORES,
    JOB_RESULTS_ROW_SCORES,
)
from nmp.evaluator.service import EvaluatorService
from nmp.evaluator.tasks import metric_results
from nmp.testing import task_harness

TEST_WORKSPACE = "test-workspace"
TEST_JOB_ID = "test-job-12345"


def task_runtime_env(tmp_path: Path) -> dict[str, str]:
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(exist_ok=True)
    results_link = storage_dir / "results"
    if not results_link.exists():
        results_link.symlink_to(tmp_path, target_is_directory=True)
    return {
        "NEMO_JOB_WORKSPACE": TEST_WORKSPACE,
        "NEMO_JOB_ID": TEST_JOB_ID,
        NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR: f"{tmp_path}/{NEMO_JOB_STEP_CONFIG_FILE_NAME}",
        PERSISTENT_JOB_STORAGE_PATH_ENVVAR: str(storage_dir),
    }


def create_test_job(sdk, workspace: str, job_id: str):
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


@pytest.fixture
def metric_job_spec() -> dict:
    return {"metric": {"type": "bleu", "references": []}, "dataset": {"rows": [{"data": "value"}]}}


@pytest.mark.integration
class TestMetricResultsTask:
    @pytest.mark.asyncio
    async def test_upload_custom_results(self, tmp_path: Path, metric_job_spec):
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
            create_test_job(ctx.sdk, TEST_WORKSPACE, TEST_JOB_ID)

            result = ctx.run_task(args=[])

            assert result.exit_code == 0, f"Task failed: {result.stderr}, exception={result.exception}"
            job_results = ctx.sdk.evaluation.metric_jobs.results.list(TEST_JOB_ID, workspace=TEST_WORKSPACE)
            result_names = [r.name for r in job_results.data]
            assert JOB_RESULTS_AGGREGATE_SCORES in result_names
            assert JOB_RESULTS_ROW_SCORES in result_names

    @pytest.mark.asyncio
    async def test_missing_results_directory(self, tmp_path: Path, metric_job_spec):
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
            assert result.exit_code != 0
            assert "FileNotFoundError" in result.stderr
