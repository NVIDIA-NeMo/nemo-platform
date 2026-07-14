# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project deployments-plugin substrate state onto ModelDeployment state."""

from typing import Any, Iterable

from nemo_deployments_plugin.entities import Deployment, Volume
from nemo_deployments_plugin.types import Endpoint
from nemo_platform.types.inference import ModelDeploymentStatus
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import format_duration

_STATUS_MAP: dict[str, ModelDeploymentStatus] = {
    "PENDING": "PENDING",
    "STARTING": "PENDING",
    "READY": "READY",
    "FAILED": "ERROR",
    "LOST": "LOST",
    "UNKNOWN": "UNKNOWN",
    "DELETING": "DELETING",
    "SUCCEEDED": "PENDING",
}


def map_status(status: str) -> ModelDeploymentStatus:
    """Map a deployments-plugin status to a ModelDeployment status."""
    return _STATUS_MAP.get(status, "UNKNOWN")


def project_host_url(endpoints: Iterable[Endpoint]) -> str | None:
    """Return the first HTTP(S) endpoint exposed by the plugin deployment."""
    return next(
        (endpoint.url for endpoint in endpoints if endpoint.protocol in {"http", "https"} and endpoint.url), None
    )


def _substrate(entity: Deployment | Volume | None) -> dict[str, Any] | None:
    if entity is None:
        return None
    return {
        "status": entity.status,
        "status_message": entity.status_message,
        "error_details": entity.error_details,
    }


# Substrate statuses that must not silently fall through to PENDING: FAILED/LOST
# are terminal (the dependent server Deployment can never satisfy its
# prerequisite), and UNKNOWN is indeterminate. Surfacing them avoids reporting a
# healthy-looking PENDING over a dead prerequisite.
_ATTENTION_SUBSTRATE_STATUSES = frozenset({"FAILED", "LOST", "UNKNOWN"})


def _substrate_issue(
    entity: Deployment | Volume | None, label: str, substrate: dict[str, Any]
) -> DeploymentStatusUpdate | None:
    if entity is None or entity.status not in _ATTENTION_SUBSTRATE_STATUSES:
        return None
    status: ModelDeploymentStatus = "UNKNOWN" if entity.status == "UNKNOWN" else "ERROR"
    return DeploymentStatusUpdate(
        status=status,
        status_message=entity.status_message or f"{label} is {entity.status}.",
        error_details={"substrate": substrate},
    )


def aggregate_status(
    volume: Volume | None,
    puller: Deployment | None,
    server: Deployment | None,
    *,
    previously_ready: bool = False,
) -> DeploymentStatusUpdate:
    """Project the three plugin entities, preferring the serving deployment."""
    substrate = {"volume": _substrate(volume), "puller": _substrate(puller), "server": _substrate(server)}
    if server is not None:
        status = map_status(server.status)
        return DeploymentStatusUpdate(
            status=status,
            status_message=server.status_message or f"Server deployment is {server.status}.",
            error_details={"substrate": substrate},
            host_url=project_host_url(server.endpoints) if status == "READY" else None,
        )
    if previously_ready:
        return DeploymentStatusUpdate(
            status="LOST",
            status_message="Serving deployment is missing after reporting READY.",
            error_details={"substrate": substrate},
        )
    issue = _substrate_issue(puller, "Weight puller", substrate) or _substrate_issue(
        volume, "Weights volume", substrate
    )
    if issue is not None:
        return issue
    return DeploymentStatusUpdate(
        status="PENDING",
        status_message="Waiting for deployments-plugin substrate resources.",
        error_details={"substrate": substrate},
    )


def build_pending_timeout_error(
    *,
    deployment_name: str,
    elapsed_seconds: float,
    timeout_seconds: int,
    substrate: dict[str, Any] | None = None,
) -> DeploymentStatusUpdate:
    """Build ERROR status when a deployment exceeds ``pending_timeout_seconds``."""
    status_msg = (
        f"Deployment '{deployment_name}' timed out after {format_duration(elapsed_seconds)} waiting for "
        f"deployments-plugin substrate to become READY (timeout: {format_duration(timeout_seconds)})."
    )
    error_details: dict[str, Any] = {
        "reason": "pending_timeout",
        "elapsed_seconds": int(elapsed_seconds),
        "timeout_seconds": timeout_seconds,
        "deployment_name": deployment_name,
    }
    if substrate is not None:
        error_details["substrate"] = substrate
    return DeploymentStatusUpdate(
        status="ERROR",
        status_message=status_msg,
        error_details=error_details,
    )


def apply_pending_timeout(
    result: DeploymentStatusUpdate,
    *,
    elapsed_seconds: float,
    timeout_seconds: int,
    deployment_name: str,
) -> DeploymentStatusUpdate:
    """Escalate a PENDING projection to ERROR once the deployment ages out."""
    if result.status != "PENDING" or elapsed_seconds < timeout_seconds:
        return result
    substrate = result.error_details.get("substrate") if result.error_details else None
    return build_pending_timeout_error(
        deployment_name=deployment_name,
        elapsed_seconds=elapsed_seconds,
        timeout_seconds=timeout_seconds,
        substrate=substrate,
    )
