# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker resource naming and identity labels for orphan cleanup."""

from __future__ import annotations

import hashlib
import re

from nemo_deployments_plugin.constants import MANAGED_BY_LABEL

MANAGED_BY_KEY = "managed-by"
DEPLOYMENT_WORKSPACE_LABEL = "nemo.nvidia.com/deployment-workspace"
DEPLOYMENT_NAME_LABEL = "nemo.nvidia.com/deployment-name"
RESTART_POLICY_LABEL = "nemo.nvidia.com/restart-policy"
CONFIG_NAME_LABEL = "nemo.nvidia.com/deployment-config"
VOLUME_WORKSPACE_LABEL = "nemo.nvidia.com/volume-workspace"
VOLUME_NAME_LABEL = "nemo.nvidia.com/volume-name"


def k8s_safe_name(base_name: str, *, max_length: int = 63, suffix: str = "") -> str:
    """Generate a DNS-label-safe name (RFC 1035) from arbitrary input."""
    hash_suffix = hashlib.sha256(base_name.encode()).hexdigest()[:8]
    normalized = re.sub(r"[^a-z0-9-]", "-", base_name.lower())
    normalized = re.sub(r"[-]+", "-", normalized)
    if normalized and not normalized[0].isalpha():
        normalized = f"x{normalized}"
    normalized = normalized.rstrip("-")

    reserved = len(suffix) + len(hash_suffix) + 1
    if len(normalized) + reserved > max_length:
        trim = max_length - reserved
        normalized = normalized[:trim].rstrip("-")
        normalized = f"{normalized}-{hash_suffix}{suffix}"
    elif suffix:
        normalized = f"{normalized}{suffix}"
    return normalized


def container_name(workspace: str, deployment_name: str) -> str:
    return k8s_safe_name(f"dep-{workspace}-{deployment_name}")


def docker_volume_name(workspace: str, volume_name: str) -> str:
    return k8s_safe_name(f"dep-vol-{workspace}-{volume_name}")


def deployment_key(workspace: str, name: str) -> str:
    return f"{workspace}/{name}"


BACKOFF_LIMIT_LABEL = "nemo.nvidia.com/backoff-limit"


def deployment_identity_labels(
    workspace: str,
    name: str,
    restart_policy: str,
    *,
    config_name: str,
    backoff_limit: int = 6,
) -> dict[str, str]:
    return {
        MANAGED_BY_KEY: MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: workspace,
        DEPLOYMENT_NAME_LABEL: name,
        RESTART_POLICY_LABEL: restart_policy,
        CONFIG_NAME_LABEL: config_name,
        BACKOFF_LIMIT_LABEL: str(backoff_limit),
    }


def volume_identity_labels(workspace: str, name: str) -> dict[str, str]:
    return {
        MANAGED_BY_KEY: MANAGED_BY_LABEL,
        VOLUME_WORKSPACE_LABEL: workspace,
        VOLUME_NAME_LABEL: name,
    }


def managed_by_filter() -> dict[str, str | bool]:
    return {"label": f"{MANAGED_BY_KEY}={MANAGED_BY_LABEL}"}
