# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Map Kubernetes Job and Deployment status to plugin DeploymentStatus values."""

from __future__ import annotations

from typing import Any

from nemo_deployments_plugin.backends.base import BackendStatusUpdate
from nemo_deployments_plugin.types import Endpoint

LOG_MAX_CHARS = 8000
CRASH_LOOP_RESTART_THRESHOLD = 3
_TRANSIENT_WAITING_REASONS = frozenset({"ContainerCreating", "PodInitializing", "ImagePullBackOff", "ErrImagePull"})


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


def _is_deployment_deleting(deployment: Any) -> bool:
    metadata = getattr(deployment, "metadata", None)
    return bool(metadata and getattr(metadata, "deletion_timestamp", None))


def missing_deployment_status(*, deployment_name: str) -> BackendStatusUpdate:
    return BackendStatusUpdate(
        status="LOST",
        status_message=(f"Deployment not found — may have been manually deleted. Expected name: {deployment_name}"),
        error_details={"expected_deployment_name": deployment_name},
    )


def _pod_restart_count(pod: Any) -> int:
    status = getattr(pod, "status", None)
    if status is None or not status.container_statuses:
        return 0
    return max(int(container_status.restart_count or 0) for container_status in status.container_statuses)


def status_message_from_pod(pod: Any) -> str | None:
    """Surface pod waiting reasons such as ImagePullBackOff or CrashLoopBackOff."""
    status = getattr(pod, "status", None)
    if status is None or not status.container_statuses:
        phase = getattr(status, "phase", None) if status is not None else None
        return f"Pod phase is {phase}" if phase else None

    for container_status in status.container_statuses:
        state = container_status.state
        if state is None:
            continue
        waiting = state.waiting
        if waiting is None:
            continue
        reason = waiting.reason or "Waiting"
        message = waiting.message or ""
        detail = f"{reason}: {message}" if message else reason
        if reason in _TRANSIENT_WAITING_REASONS or reason == "CrashLoopBackOff":
            return detail
    phase = status.phase or "Unknown"
    return f"Pod phase is {phase}"


def pod_failure_status(*, deployment_name: str, pod: Any) -> BackendStatusUpdate | None:
    """Return FAILED when a pod is in a sustained crash loop."""
    status = getattr(pod, "status", None)
    if status is None or not status.container_statuses:
        return None
    restart_count = _pod_restart_count(pod)
    if restart_count < CRASH_LOOP_RESTART_THRESHOLD:
        return None
    for container_status in status.container_statuses:
        state = container_status.state
        if state is None or state.waiting is None:
            continue
        reason = state.waiting.reason or ""
        if reason != "CrashLoopBackOff":
            continue
        message = state.waiting.message or ""
        detail = f"{reason}: {message}" if message else reason
        return BackendStatusUpdate(
            status="FAILED",
            status_message=f"Deployment {deployment_name} pod crash loop: {detail}",
        )
    return None


def status_from_deployment(
    *,
    deployment: Any,
    deployment_name: str,
    expected_labels: dict[str, str],
    endpoints: list[Endpoint],
    pod: Any | None = None,
) -> BackendStatusUpdate:
    """Map a Deployment object to plugin status, with optional pod drill-down."""
    if not resource_labels_match(deployment, expected_labels):
        return BackendStatusUpdate(
            status="FAILED",
            status_message=f"Deployment {deployment_name} exists but is not managed by this plugin",
        )
    if _is_deployment_deleting(deployment):
        return BackendStatusUpdate(
            status="DELETING",
            status_message=f"Deployment {deployment_name} is terminating",
        )

    dep_status = deployment.status
    ready_replicas = int(dep_status.ready_replicas or 0) if dep_status is not None else 0
    if ready_replicas >= 1:
        return BackendStatusUpdate(
            status="READY",
            status_message=f"Deployment {deployment_name} is ready",
            endpoints=endpoints,
        )

    if pod is not None:
        failure = pod_failure_status(deployment_name=deployment_name, pod=pod)
        if failure is not None:
            return failure
        pod_message = status_message_from_pod(pod)
        if pod_message:
            return BackendStatusUpdate(
                status="STARTING",
                status_message=f"Deployment {deployment_name}: {pod_message}",
            )

    return BackendStatusUpdate(
        status="STARTING",
        status_message=f"Deployment {deployment_name} is starting",
    )
