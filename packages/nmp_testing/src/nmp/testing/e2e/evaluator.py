# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluator-specific E2E test helpers.

These helpers are used by tests under `e2e/evaluator/` but live in `nmp.testing`
so test modules do not need to import from `conftest.py`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import cast

from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import AggregatedMetricResult, MetricEvaluationJob, RowScore
from nemo_platform.types.shared import PlatformJobStatusResponse
from nmp.testing.e2e.jobs import poll_until_terminal

# Terminal job statuses
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "error"}

# Expected result artifact names
AGGREGATE_SCORES_RESULT = "aggregate-scores"
ROW_SCORES_RESULT = "row-scores"


def wait_for_evaluation_job(
    sdk: NeMoPlatform,
    job_name: str,
    workspace: str,
    timeout: float = 120.0,
    image_pull_timeout: float = 600.0,
    poll_interval: float = 2.0,
    expected_status: str | None = None,
    raise_on_error: bool = True,
) -> MetricEvaluationJob:
    """Wait for an evaluator metrics job to reach a terminal state.

    Time spent in ``pending`` status (e.g. pulling a container image) is not
    counted against *timeout*. A separate *image_pull_timeout* caps how long
    the job may remain pending before the test fails.

    Args:
        raise_on_error: If True (default) and ``expected_status`` is not set,
            raise an ``AssertionError`` when the job ends in "error" or
            "failed" status.  Set to False for tests that intentionally
            exercise failure conditions.
    """
    terminal = {expected_status} if expected_status else TERMINAL_STATUSES
    last_job: MetricEvaluationJob = sdk.evaluation.metric_jobs.retrieve(job_name, workspace=workspace)

    def get_status() -> str:
        nonlocal last_job
        last_job = sdk.evaluation.metric_jobs.retrieve(job_name, workspace=workspace)
        return last_job.status.lower() if last_job.status else ""

    poll_until_terminal(
        get_status,
        label=job_name,
        terminal=terminal,
        timeout=timeout,
        image_pull_timeout=image_pull_timeout,
        poll_interval=poll_interval,
    )

    if last_job is None:
        last_job = sdk.evaluation.metric_jobs.retrieve(job_name, workspace=workspace)
    if last_job is None:
        raise RuntimeError(f"Job '{job_name}' could not be retrieved after polling completed.")

    if raise_on_error and expected_status is None and last_job.status in ("error", "failed"):
        status_response = sdk.evaluation.metric_jobs.get_status(job_name, workspace=workspace)
        raise AssertionError(
            f"Job '{job_name}' ended with status '{last_job.status}' — expected 'completed'.\n"
            f"Status details: {status_response}"
        )

    return last_job


@dataclass
class JobOutputs:
    """Container for all job outputs."""

    job: MetricEvaluationJob
    job_status: PlatformJobStatusResponse | None
    aggregate_scores: AggregatedMetricResult | None
    row_scores: list[RowScore] | None
    logs: list[str]


def get_job_outputs(
    sdk: NeMoPlatform,
    job_name: str,
    workspace: str,
) -> JobOutputs:
    """Retrieve all outputs from an evaluator metrics job."""
    job = sdk.evaluation.metric_jobs.retrieve(job_name, workspace=workspace)
    job_status = sdk.evaluation.metric_jobs.get_status(job_name, workspace=workspace)

    # Smoke-test the generic results.download endpoint (status + body readable).
    # Content is validated below via the typed aggregate_scores/row_scores accessors.
    results = sdk.evaluation.metric_jobs.results.list(job_name, workspace=workspace)
    for result in results.data:
        if result.name in (AGGREGATE_SCORES_RESULT, ROW_SCORES_RESULT):
            response = sdk.evaluation.metric_jobs.results.download(
                result.name,
                job=job_name,
                workspace=workspace,
            )
            response.read()

    # Verify result entity is registered
    job_result = sdk.evaluation.metric_job_results.retrieve(job_name, workspace=workspace)

    # Fetch serialized results from file
    aggregate_scores = sdk.evaluation.metric_jobs.results.aggregate_scores.download(job_name, workspace=workspace)
    row_scores = sdk.evaluation.metric_jobs.results.row_scores.download(job_name, workspace=workspace)

    assert job_result.scores == aggregate_scores.scores

    logs_response = sdk.evaluation.metric_jobs.get_logs(job_name, workspace=workspace)
    logs = [log.message for log in logs_response.data if log.message]

    return JobOutputs(
        job=job,
        job_status=job_status,
        aggregate_scores=aggregate_scores,
        row_scores=list(row_scores),
        logs=logs,
    )


def verify_job_completed_successfully(
    outputs: JobOutputs,
    *,
    require_samples_processed: bool = True,
    require_row_scores: bool = True,
) -> None:
    """Assert that a job completed successfully with expected outputs.

    Args:
        outputs: Job outputs from get_job_outputs.
        require_row_scores: If True, assert row_scores are present and non-empty.
            Set to False for EvalFactory-based metrics (e.g. retriever) that only
            produce aggregate-scores.
    """
    if outputs.job.status != "completed":
        error_msg = f"Job status is '{outputs.job.status}', expected 'completed'"
        if outputs.logs:
            error_msg += f"\n\nJob logs:\n{outputs.logs}"
        if outputs.job_status:
            error_msg += f"\n\nStatus details: {outputs.job_status}"
        raise AssertionError(error_msg)

    # Verify status_details is updated
    assert outputs.job_status is not None, "Status details should be present"
    assert outputs.job_status.status_details is not None
    assert outputs.job_status.status_details.get("progress") == 100.0, (
        f"Expect 100% progress completed for successful jobs: {outputs.job_status}"
    )
    if require_samples_processed:
        samples_processed = cast(int, outputs.job_status.status_details.get("samples_processed", 0))
        assert samples_processed > 0, (
            f"Expect samples_processed for custom jobs and industry metrics with limit_samples: {outputs.job_status}"
        )

    assert outputs.aggregate_scores is not None, "Aggregate scores should be present"
    assert len(outputs.aggregate_scores.scores) > 0, "Aggregate scores should have 'scores' key"

    if require_row_scores:
        assert outputs.row_scores is not None, "Row scores should be present"
        len_row_scores = len(outputs.row_scores)
        assert len_row_scores > 0, "Row scores should not be empty"
        if require_samples_processed:
            samples_processed = cast(int, outputs.job_status.status_details.get("samples_processed", 0))
            assert samples_processed >= len_row_scores, (
                f"Expect samples_processed to match number of rows: {outputs.job_status}"
            )


def output_metric_job_logs(sdk: NeMoPlatform, job_name: str, workspace: str, dir: str | None = None):
    """Output job logs for debugging failed tests"""
    logs_dir = dir or os.getenv("JOB_LOGS_DIR")
    if logs_dir:
        os.makedirs(logs_dir, exist_ok=True)
        with open(f"{logs_dir}/{job_name}.log", "w") as f:
            for log_entry in sdk.evaluation.metric_jobs.get_logs(job_name, workspace=workspace):
                f.write(f"[{log_entry.timestamp}] {log_entry.message}\n")
    else:
        for log_entry in sdk.evaluation.metric_jobs.get_logs(job_name, workspace=workspace):
            print(f"[{log_entry.timestamp}] {log_entry.message}")


def output_benchmark_job_logs(sdk: NeMoPlatform, job_name: str, workspace: str, dir: str | None = None):
    """Output job logs for debugging failed tests"""
    logs_dir = dir or os.getenv("JOB_LOGS_DIR")
    if logs_dir:
        os.makedirs(logs_dir, exist_ok=True)
        with open(f"{logs_dir}/{job_name}.log", "w") as f:
            for log_entry in sdk.evaluation.benchmark_jobs.get_logs(job_name, workspace=workspace):
                f.write(f"[{log_entry.timestamp}] {log_entry.message}\n")
    else:
        for log_entry in sdk.evaluation.benchmark_jobs.get_logs(job_name, workspace=workspace):
            print(f"[{log_entry.timestamp}] {log_entry.message}")


def upload_dataset_to_fileset(
    sdk: NeMoPlatform,
    workspace: str,
    fileset_name: str,
    rows: list[dict],
    filename: str = "dataset.json",
) -> str:
    """Upload dataset rows to a fileset as JSON and return the FilesetRef string."""
    json_content = json.dumps(rows, indent=2)

    sdk.files.upload_content(
        content=json_content,
        remote_path=filename,
        fileset=fileset_name,
        workspace=workspace,
    )

    return f"{workspace}/{fileset_name}"


def create_dataset_fileset(
    sdk: NeMoPlatform,
    workspace: str,
    fileset_name: str,
    rows: list[dict],
    *,
    schema: dict | None = None,
    filename: str = "dataset.json",
) -> str:
    """Create a fileset with optional dataset schema metadata and upload rows."""
    if schema is not None:
        sdk.files.filesets.create(
            workspace=workspace,
            name=fileset_name,
            metadata={"dataset": {"schema": schema}},
        )
    else:
        sdk.files.filesets.create(workspace=workspace, name=fileset_name)
    return upload_dataset_to_fileset(sdk, workspace, fileset_name, rows, filename=filename)


def upload_beir_dataset_to_fileset(
    sdk: NeMoPlatform,
    workspace: str,
    fileset_name: str,
    queries: list[dict],
    corpus: list[dict],
    qrels: list[tuple[str, str, int]],
) -> str:
    """Upload a BEIR-format dataset to a fileset and return the FilesetRef string.

    BEIR format requires three files:
    - corpus.jsonl: Documents with _id, title, text
    - queries.jsonl: Queries with _id, text
    - qrels/test.tsv: Tab-separated relevance judgments (query-id, corpus-id, score)

    Args:
        sdk: NeMoPlatform client.
        workspace: Workspace name.
        fileset_name: Fileset name to upload to (must already exist).
        queries: List of dicts with keys: _id, text.
        corpus: List of dicts with keys: _id, title, text.
        qrels: List of (query_id, corpus_id, score) tuples.

    Returns:
        FilesetRef string (workspace/fileset_name).
    """
    # Upload corpus.jsonl
    corpus_content = "\n".join(json.dumps(doc) for doc in corpus) + "\n"
    sdk.files.upload_content(
        content=corpus_content,
        remote_path="corpus.jsonl",
        fileset=fileset_name,
        workspace=workspace,
    )

    # Upload queries.jsonl
    queries_content = "\n".join(json.dumps(q) for q in queries) + "\n"
    sdk.files.upload_content(
        content=queries_content,
        remote_path="queries.jsonl",
        fileset=fileset_name,
        workspace=workspace,
    )

    # Upload qrels/test.tsv (tab-separated: query-id, corpus-id, score)
    qrels_lines = ["query-id\tcorpus-id\tscore"]
    for query_id, corpus_id, score in qrels:
        qrels_lines.append(f"{query_id}\t{corpus_id}\t{score}")
    qrels_content = "\n".join(qrels_lines) + "\n"
    sdk.files.upload_content(
        content=qrels_content,
        remote_path="qrels/test.tsv",
        fileset=fileset_name,
        workspace=workspace,
    )

    return f"{workspace}/{fileset_name}"
