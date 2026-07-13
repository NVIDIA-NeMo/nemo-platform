# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project deployments-plugin substrate state onto ModelDeployment state."""

from typing import Any, Iterable

from nemo_deployments_plugin.entities import Deployment, Volume
from nemo_deployments_plugin.types import Endpoint
from nemo_platform.types.inference import ModelDeploymentStatus
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate

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
    if puller is not None and puller.status == "FAILED":
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=puller.status_message or "Weight puller failed.",
            error_details={"substrate": substrate},
        )
    if volume is not None and volume.status == "FAILED":
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=volume.status_message or "Weights volume failed.",
            error_details={"substrate": substrate},
        )
    return DeploymentStatusUpdate(
        status="PENDING",
        status_message="Waiting for deployments-plugin substrate resources.",
        error_details={"substrate": substrate},
    )
