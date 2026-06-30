# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for deployment identity labels."""

from __future__ import annotations

from nemo_deployments_plugin.backends.docker.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    container_name,
    deployment_identity_labels,
    docker_volume_name,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL


def test_container_name_is_dns_safe() -> None:
    name = container_name("my-workspace", "my.deployment")
    assert name.startswith("dep-")
    assert len(name) <= 63


def test_docker_volume_name_prefix() -> None:
    assert docker_volume_name("ws", "vol").startswith("dep-vol-")


def test_deployment_identity_labels() -> None:
    labels = deployment_identity_labels(
        "default",
        "srv",
        "Always",
        config_name="cfg1",
    )
    assert labels[MANAGED_BY_KEY] == MANAGED_BY_LABEL
    assert labels[DEPLOYMENT_WORKSPACE_LABEL] == "default"
    assert labels[DEPLOYMENT_NAME_LABEL] == "srv"
    assert labels[CONFIG_NAME_LABEL] == "cfg1"
