# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared deployment/volume identity labels and substrate-safe resource naming.

Naming uses ``nemo_platform_plugin.k8s_naming`` (plugins cannot import ``nmp_common``).
Identity labels drive orphan cleanup and idempotency across docker and k8s backends.

Label domain is ``nemo.nvidia.com/*`` (deployments plugin scope). Core services such as
jobs and models use ``nmp.nvidia.com/*`` today; converging prefixes is out of scope for 757.

Deployment and volume resources use separate workspace label keys
(``deployment-workspace`` vs ``volume-workspace``) so list/watch queries can target one
resource kind without ambiguous selectors, even though the workspace value is the same string.
"""

from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_platform_plugin.k8s_naming import k8s_safe_name, workspace_name_identity

MANAGED_BY_KEY = "managed-by"
DEPLOYMENT_WORKSPACE_LABEL = "nemo.nvidia.com/deployment-workspace"
DEPLOYMENT_NAME_LABEL = "nemo.nvidia.com/deployment-name"
RESTART_POLICY_LABEL = "nemo.nvidia.com/restart-policy"
CONFIG_NAME_LABEL = "nemo.nvidia.com/deployment-config"
VOLUME_WORKSPACE_LABEL = "nemo.nvidia.com/volume-workspace"
VOLUME_NAME_LABEL = "nemo.nvidia.com/volume-name"
BACKOFF_LIMIT_LABEL = "nemo.nvidia.com/backoff-limit"


def deployment_key(workspace: str, name: str) -> str:
    """Return the canonical identity string used for hashing and label keys."""
    return workspace_name_identity(workspace, name)


def container_name(workspace: str, deployment_name: str) -> str:
    """Docker container name for a deployment (``dep-`` prefix, hashed identity)."""
    return k8s_deployment_resource_name(workspace, deployment_name)


def docker_volume_name(workspace: str, volume_name: str) -> str:
    """Docker volume name for a deployment volume (``dep-vol-`` prefix, hashed identity)."""
    return k8s_volume_resource_name(workspace, volume_name)


def k8s_deployment_resource_name(workspace: str, deployment_name: str) -> str:
    """Kubernetes resource name for a deployment (Deployment, Job, Service, etc.)."""
    return k8s_safe_name(
        f"dep-{workspace}-{deployment_name}",
        hash_input=deployment_key(workspace, deployment_name),
    )


def k8s_volume_resource_name(workspace: str, volume_name: str) -> str:
    """Kubernetes PVC name for a deployment volume."""
    return k8s_safe_name(
        f"dep-vol-{workspace}-{volume_name}",
        hash_input=deployment_key(workspace, volume_name),
    )


def deployment_identity_labels(
    workspace: str,
    name: str,
    restart_policy: str,
    *,
    config_name: str,
    backoff_limit: int = 6,
) -> dict[str, str]:
    """Return identity labels attached to deployment backend resources."""
    return {
        MANAGED_BY_KEY: MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: workspace,
        DEPLOYMENT_NAME_LABEL: name,
        RESTART_POLICY_LABEL: restart_policy,
        CONFIG_NAME_LABEL: config_name,
        BACKOFF_LIMIT_LABEL: str(backoff_limit),
    }


def volume_identity_labels(workspace: str, name: str) -> dict[str, str]:
    """Return identity labels attached to volume backend resources."""
    return {
        MANAGED_BY_KEY: MANAGED_BY_LABEL,
        VOLUME_WORKSPACE_LABEL: workspace,
        VOLUME_NAME_LABEL: name,
    }


def managed_by_filter() -> dict[str, str]:
    """Return a Docker SDK filter dict for plugin-managed resources."""
    return {"label": f"{MANAGED_BY_KEY}={MANAGED_BY_LABEL}"}


def managed_by_label_selector() -> str:
    """Kubernetes label selector for plugin-managed resources."""
    return f"{MANAGED_BY_KEY}={MANAGED_BY_LABEL}"
