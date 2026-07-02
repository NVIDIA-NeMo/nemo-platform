# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from backends.k8s.k8s_helpers import job_identity_labels, mock_job
from nemo_deployments_plugin.backends.k8s.status import missing_job_status, status_from_job


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
