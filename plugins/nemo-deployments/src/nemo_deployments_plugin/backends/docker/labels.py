# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker resource naming and identity labels for orphan cleanup.

Resource names are derived from a human-readable prefix plus a deterministic
8-character hash. The hash is computed from ``{workspace}/{name}`` (see
``deployment_key``), not from the hyphen-joined display string, so ambiguous
pairs like ``("foo", "bar-baz")`` and ``("foo-bar", "baz")`` produce distinct
names even when their joined prefixes collide.

Orphan cleanup and idempotency rely on identity labels, not container names
alone. Existing containers keep their pre-change names after upgrade; only new
deployments receive hashed names.
"""

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

_HASH_SUFFIX_LENGTH = 8


def k8s_safe_name(
    base_name: str,
    *,
    max_length: int = 63,
    suffix: str = "",
    hash_input: str | None = None,
) -> str:
    """Generate a DNS-label-safe name (RFC 1035) with a mandatory hash suffix.

    Normalizes ``base_name`` for display, truncates when needed, then returns
    ``{normalized}-{hash8}{suffix}``. The hash is SHA-256 of ``hash_input`` when
    provided, otherwise ``base_name``. Callers that represent a workspace/name
    pair should pass ``hash_input=deployment_key(workspace, name)`` so the hash
    reflects the unambiguous identity rather than the join-ambiguous prefix.
    """
    hash_source = hash_input if hash_input is not None else base_name
    hash_suffix = hashlib.sha256(hash_source.encode()).hexdigest()[:_HASH_SUFFIX_LENGTH]
    normalized = re.sub(r"[^a-z0-9-]", "-", base_name.lower())
    normalized = re.sub(r"[-]+", "-", normalized)
    if normalized and not normalized[0].isalpha():
        normalized = f"x{normalized}"
    normalized = normalized.rstrip("-")

    reserved = len(suffix) + len(hash_suffix) + 1
    if len(normalized) + reserved > max_length:
        normalized = normalized[: max_length - reserved].rstrip("-")
    if not normalized:
        normalized = "x"
    return f"{normalized}-{hash_suffix}{suffix}"


def deployment_key(workspace: str, name: str) -> str:
    """Return the canonical identity string used for hashing and label keys."""
    return f"{workspace}/{name}"


def container_name(workspace: str, deployment_name: str) -> str:
    """Docker container name for a deployment (``dep-`` prefix, hashed identity)."""
    return k8s_safe_name(
        f"dep-{workspace}-{deployment_name}",
        hash_input=deployment_key(workspace, deployment_name),
    )


def docker_volume_name(workspace: str, volume_name: str) -> str:
    """Docker volume name for a deployment volume (``dep-vol-`` prefix, hashed identity)."""
    return k8s_safe_name(
        f"dep-vol-{workspace}-{volume_name}",
        hash_input=deployment_key(workspace, volume_name),
    )


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
