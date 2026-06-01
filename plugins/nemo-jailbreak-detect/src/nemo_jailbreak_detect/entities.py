# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entity definitions for the jailbreak-detection plugin.

A :class:`JailbreakDetectorDeployment` is the single source of truth for one
self-hosted model server. The service writes the *desired* fields; the
controller reconciles reality and writes back the *observed* fields
(``status``, ``endpoint_url``, ``handle``, ``last_error``).
"""

from __future__ import annotations

from typing import Literal

from nemo_platform_plugin.entity import NemoEntity

DeploymentStatus = Literal[
    "pending",  # created, not yet acted on
    "starting",  # backend asked to start; waiting for readiness
    "running",  # healthy and serving
    "failed",  # backend reported failure or health check exhausted
    "stopping",  # marked for teardown
    "stopped",  # torn down
]


class JailbreakDetectorDeployment(NemoEntity, entity_type="jailbreak_detect_deployment"):
    """A self-hosted NemoGuard JailbreakDetect model server deployment."""

    # --- desired state (set by the service) ---
    backend: Literal["docker", "jobs"] = "docker"
    image: str | None = None
    device: str | None = None
    port: int | None = None

    # --- observed state (set by the controller) ---
    status: DeploymentStatus = "pending"
    endpoint_url: str | None = None
    handle: str | None = None  # backend-specific id (container id / job name)
    last_error: str | None = None
