# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify that the agent set up an evaluation job via CLI.

Tests workspace/fileset creation, dataset upload, metric creation, and job creation.
Note: Job execution (completion, results) is not tested because the
quickstart environment does not include the job execution worker.
"""

import os

from nemo_platform import NeMoPlatform

WORKSPACE = "eval-test-workspace"
FILESET = "eval-dataset"


def _get_client() -> NeMoPlatform:
    nmp_base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
    return NeMoPlatform(base_url=nmp_base_url)


def test_workspace_exists():
    """Verify the eval-test-workspace was created."""
    client = _get_client()
    response = client.workspaces.list()
    workspace_names = [ws.name for ws in response.data]
    assert WORKSPACE in workspace_names, f"Workspace '{WORKSPACE}' not found. Found: {workspace_names}"


def test_fileset_exists():
    """Verify the eval-dataset fileset was created."""
    client = _get_client()
    response = client.files.filesets.list(workspace=WORKSPACE)
    fileset_names = [fs.name for fs in response.data]
    assert FILESET in fileset_names, f"Fileset '{FILESET}' not found. Found: {fileset_names}"


def test_fileset_has_data():
    """Verify the dataset was uploaded to the fileset."""
    client = _get_client()
    files = client.files.list(fileset=FILESET, workspace=WORKSPACE)
    assert len(files.data) > 0, f"Fileset '{FILESET}' has no files uploaded"


def test_metric_created():
    """Verify a string-check metric was created in the workspace."""
    client = _get_client()
    response = client.evaluation.metrics.list(workspace=WORKSPACE)
    metrics = response.data
    string_check_metrics = [m for m in metrics if m.type == "string-check"]
    assert len(string_check_metrics) > 0, (
        f"No string-check metrics found in workspace '{WORKSPACE}'. Found metric types: {[m.type for m in metrics]}"
    )


def test_evaluation_job_created():
    """Verify that at least one evaluation metric job was created."""
    client = _get_client()
    jobs = client.evaluation.metric_jobs.list(workspace=WORKSPACE)
    assert len(jobs.data) > 0, "No evaluation metric jobs found"

    job = jobs.data[0]
    assert job.spec is not None, "Job has no spec"
