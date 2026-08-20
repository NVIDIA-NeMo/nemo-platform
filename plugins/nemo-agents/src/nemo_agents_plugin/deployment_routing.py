# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared endpoint resolution for agent deployments."""

from nemo_agents_plugin.entities import AgentDeployment, is_container_deployment_mode


def get_deployment_endpoint(deployment: AgentDeployment) -> str | None:
    """Return the HTTP address for a subprocess or container deployment."""
    if is_container_deployment_mode(deployment.deployment_mode):
        for endpoint in deployment.endpoints:
            if endpoint.protocol in ("http", "https") and endpoint.url:
                return endpoint.url
        return None
    return deployment.endpoint or None


def is_deployment_routable(deployment: AgentDeployment) -> bool:
    """Return whether a running deployment currently has a resolvable endpoint."""
    return deployment.status == "running" and get_deployment_endpoint(deployment) is not None
