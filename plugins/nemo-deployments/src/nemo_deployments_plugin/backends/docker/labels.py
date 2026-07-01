# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker resource naming and identity labels (re-exported from shared ``backends.labels``)."""

from nemo_deployments_plugin.backends.labels import (
    BACKOFF_LIMIT_LABEL,
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    RESTART_POLICY_LABEL,
    VOLUME_NAME_LABEL,
    VOLUME_WORKSPACE_LABEL,
    container_name,
    deployment_identity_labels,
    deployment_key,
    docker_volume_name,
    managed_by_filter,
    volume_identity_labels,
)

__all__ = [
    "BACKOFF_LIMIT_LABEL",
    "CONFIG_NAME_LABEL",
    "DEPLOYMENT_NAME_LABEL",
    "DEPLOYMENT_WORKSPACE_LABEL",
    "MANAGED_BY_KEY",
    "RESTART_POLICY_LABEL",
    "VOLUME_NAME_LABEL",
    "VOLUME_WORKSPACE_LABEL",
    "container_name",
    "deployment_identity_labels",
    "deployment_key",
    "docker_volume_name",
    "managed_by_filter",
    "volume_identity_labels",
]
