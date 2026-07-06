# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from backends.k8s.k8s_helpers import (
    always_identity_labels,
    job_identity_labels,
    mock_deployment,
    mock_job,
    mock_pod,
    sample_always_config,
)
from nemo_deployments_plugin.backends.k8s.deployments import build_in_cluster_endpoints
from nemo_deployments_plugin.backends.k8s.status import (
    missing_deployment_status,
    missing_job_status,
    status_from_deployment,
    status_from_job,
)
from nemo_deployments_plugin.backends.labels import k8s_deployment_resource_name


@pytest.mark.parametrize(
    ("job", "expected_status", "message_substring"),
    [
        (lambda: mock_job(complete=True), "SUCCEEDED", "completed successfully"),
        (lambda: mock_job(restart_policy="OnFailure", failed=True), "FAILED", "BackoffLimitExceeded"),
        (lambda: mock_job(active=1), "STARTING", "active pod"),
        (lambda: mock_job(deleting=True), "DELETING", "terminating"),
    ],
)
def test_status_from_job(job, expected_status: str, message_substring: str) -> None:
    labels = job_identity_labels()
    if expected_status == "FAILED":
        labels = job_identity_labels(restart_policy="OnFailure")
    update = status_from_job(
        job=job(),
        job_name="dep-default-task-abc12345",
        expected_labels=labels,
    )
    assert update.status == expected_status
    assert message_substring in update.status_message


def test_missing_job_status() -> None:
    update = missing_job_status(job_name="dep-default-task-abc12345")
    assert update.status == "FAILED"
    assert "not found" in update.status_message


def test_missing_deployment_status_is_lost() -> None:
    update = missing_deployment_status(deployment_name="dep-default-task-abc12345")
    assert update.status == "LOST"


@pytest.mark.parametrize(
    ("ready_replicas", "deleting", "pod", "expected_status", "message_substring"),
    [
        (1, False, None, "READY", "ready"),
        (0, False, mock_pod(waiting_reason="ImagePullBackOff"), "STARTING", "ImagePullBackOff"),
        (0, False, mock_pod(waiting_reason="CrashLoopBackOff", restart_count=1), "STARTING", "CrashLoopBackOff"),
        (0, False, mock_pod(waiting_reason="CrashLoopBackOff", restart_count=3), "FAILED", "CrashLoopBackOff"),
        (0, True, None, "DELETING", "terminating"),
    ],
)
def test_status_from_deployment(ready_replicas, deleting, pod, expected_status, message_substring) -> None:
    resource_name = k8s_deployment_resource_name("default", "task")
    labels = always_identity_labels()
    deployment = mock_deployment(ready_replicas=ready_replicas, deleting=deleting)
    endpoints = build_in_cluster_endpoints(
        resource_name=resource_name,
        namespace="default",
        containers=tuple(sample_always_config().containers),
    )
    update = status_from_deployment(
        deployment=deployment,
        deployment_name=resource_name,
        expected_labels=labels,
        endpoints=endpoints,
        pod=pod,
    )
    assert update.status == expected_status
    assert message_substring in update.status_message
