# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Idempotency tests for DockerDeploymentBackend.create_deployment."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backends.docker.docker_helpers import container_attrs, sample_config
from nemo_deployments_plugin.backends.docker.backend import DockerDeploymentBackend
from nemo_deployments_plugin.backends.docker.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    RESTART_POLICY_LABEL,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL


@pytest.mark.asyncio
async def test_create_existing_matching_container_returns_read_status(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    existing = MagicMock()
    existing.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESTART_POLICY_LABEL: "Always",
        CONFIG_NAME_LABEL: "cfg1",
    }
    existing.id = "abc"
    existing.status = "running"
    existing.ports = {}
    existing.attrs = container_attrs()
    mock_docker_client.containers.get.return_value = existing
    mock_entities.get.return_value = sample_config()

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "READY"
    mock_docker_client.containers.run.assert_not_called()
