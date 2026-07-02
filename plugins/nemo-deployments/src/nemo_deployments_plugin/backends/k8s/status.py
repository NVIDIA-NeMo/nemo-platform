# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Map Kubernetes Job status to plugin DeploymentStatus values."""

from __future__ import annotations

from typing import Any

from nemo_deployments_plugin.backends.base import BackendStatusUpdate

LOG_MAX_CHARS = 8000


def _job_is_deleting(job: Any) -> bool:
    metadata = getattr(job, "metadata", None)
    return bool(metadata and getattr(metadata, "deletion_timestamp", None))


def resource_labels_match(resource: Any, expected_labels: dict[str, str]) -> bool:
    metadata = getattr(resource, "metadata", None)
    if metadata is None or not metadata.labels:
        return False
    return all(metadata.labels.get(key) == value for key, value in expected_labels.items())


def _job_labels_match(job: Any, expected_labels: dict[str, str]) -> bool:
    return resource_labels_match(job, expected_labels)


def _job_condition(job: Any, condition_type: str) -> Any | None:
    status = getattr(job, "status", None)
    if status is None or not status.conditions:
        return None
    for condition in status.conditions:
        if condition.type == condition_type:
            return condition
    return None


def missing_job_status(*, job_name: str) -> BackendStatusUpdate:
    return BackendStatusUpdate(
        status="FAILED",
        status_message=f"Job not found. Expected name: {job_name}",
        error_details={"expected_job_name": job_name},
    )


def status_from_job(
    *,
    job: Any,
    job_name: str,
    expected_labels: dict[str, str],
) -> BackendStatusUpdate:
    """Map a Job object to plugin status, enforcing identity labels and delete propagation."""
    if not _job_labels_match(job, expected_labels):
        return BackendStatusUpdate(
            status="FAILED",
            status_message=f"Job {job_name} exists but is not managed by this plugin",
        )
    if _job_is_deleting(job):
        return BackendStatusUpdate(status="DELETING", status_message=f"Job {job_name} is terminating")

    complete = _job_condition(job, "Complete")
    if complete is not None and complete.status == "True":
        return BackendStatusUpdate(
            status="SUCCEEDED",
            status_message=f"Job {job_name} completed successfully",
        )

    failed = _job_condition(job, "Failed")
    if failed is not None and failed.status == "True":
        message = failed.message or f"Job {job_name} failed"
        return BackendStatusUpdate(status="FAILED", status_message=message)

    status = job.status
    active_pods = int(status.active or 0) if status is not None else 0
    if active_pods > 0:
        return BackendStatusUpdate(
            status="STARTING",
            status_message=f"Job {job_name} is running ({active_pods} active pod(s))",
        )

    return BackendStatusUpdate(status="STARTING", status_message=f"Job {job_name} is pending")
