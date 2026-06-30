# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Map Docker container state to plugin DeploymentStatus values."""

from __future__ import annotations

from nemo_deployments_plugin.backends.base import BackendStatusUpdate
from nemo_deployments_plugin.types import DeploymentStatus, RestartPolicy

LOG_TAIL_LINES = 80
LOG_MAX_CHARS = 8000
SUCCESSFUL_EXIT_CODES = (0,)


def format_duration(seconds: float) -> str:
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def map_exited_status(exit_code: int, restart_policy: RestartPolicy) -> DeploymentStatus:
    """Map a stopped container's exit code to a terminal deployment status.

    Restart-policy-specific retry handling happens in the backend before this
    helper is called for non-zero exits.
    """
    del restart_policy
    if exit_code in SUCCESSFUL_EXIT_CODES:
        return "SUCCEEDED"
    return "FAILED"


def missing_container_status(restart_policy: RestartPolicy, *, container_name: str) -> BackendStatusUpdate:
    if restart_policy == "Always":
        return BackendStatusUpdate(
            status="LOST",
            status_message=(f"Container not found — may have been manually deleted. Expected name: {container_name}"),
            error_details={"expected_container_name": container_name},
        )
    return BackendStatusUpdate(
        status="FAILED",
        status_message=f"Container not found. Expected name: {container_name}",
        error_details={"expected_container_name": container_name},
    )


def map_docker_state_to_starting(container_id: str, state: str) -> BackendStatusUpdate:
    return BackendStatusUpdate(
        status="STARTING",
        status_message=f"Container is {state} (ID: {container_id[:12]})",
    )
