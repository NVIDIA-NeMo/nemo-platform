# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from backends.k8s.k8s_helpers import job_identity_labels, mock_job
from nemo_deployments_plugin.backends.k8s.status import missing_job_status, status_from_job


def test_status_from_job_complete() -> None:
    labels = job_identity_labels()
    update = status_from_job(
        job=mock_job(complete=True),
        job_name="dep-default-task-abc12345",
        expected_labels=labels,
        restart_policy="Never",
    )
    assert update.status == "SUCCEEDED"


def test_status_from_job_failed() -> None:
    labels = job_identity_labels(restart_policy="OnFailure")
    update = status_from_job(
        job=mock_job(restart_policy="OnFailure", failed=True),
        job_name="dep-default-task-abc12345",
        expected_labels=labels,
        restart_policy="OnFailure",
    )
    assert update.status == "FAILED"
    assert "BackoffLimitExceeded" in update.status_message


def test_status_from_job_active_is_starting() -> None:
    labels = job_identity_labels()
    update = status_from_job(
        job=mock_job(active=1),
        job_name="dep-default-task-abc12345",
        expected_labels=labels,
        restart_policy="Never",
    )
    assert update.status == "STARTING"
    assert "active pod" in update.status_message


def test_status_from_job_deleting() -> None:
    labels = job_identity_labels()
    update = status_from_job(
        job=mock_job(deleting=True),
        job_name="dep-default-task-abc12345",
        expected_labels=labels,
        restart_policy="Never",
    )
    assert update.status == "DELETING"


def test_missing_job_status() -> None:
    update = missing_job_status(job_name="dep-default-task-abc12345")
    assert update.status == "FAILED"
    assert "not found" in update.status_message
