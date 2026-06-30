# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mocked docker client tests for DockerDeploymentBackend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backends.docker.docker_helpers import container_attrs, sample_config
from docker.errors import APIError, NotFound
from nemo_deployments_plugin.backends.docker.backend import DockerDeploymentBackend
from nemo_deployments_plugin.backends.docker.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    RESTART_POLICY_LABEL,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Deployment


@pytest.mark.asyncio
async def test_create_deployment_starts_container(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.return_value = MagicMock(id="abc123")

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={"docker": {"port_range_start": 9000, "port_range_end": 9100}},
    )

    assert update.status == "STARTING"
    mock_docker_client.containers.run.assert_called_once()
    mock_entities.get.assert_awaited()


@pytest.mark.asyncio
async def test_read_status_ready_when_running_without_probe(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    container = MagicMock()
    container.id = "abc123def456"
    container.status = "running"
    container.labels = {
        "managed-by": MANAGED_BY_LABEL,
        RESTART_POLICY_LABEL: "Always",
        CONFIG_NAME_LABEL: "cfg1",
    }
    container.ports = {}
    container.attrs = container_attrs()
    mock_docker_client.containers.get.return_value = container
    mock_entities.get.return_value = sample_config()

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"


@pytest.mark.asyncio
async def test_read_status_lost_when_missing_always(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    deployment_entity = MagicMock()
    deployment_entity.deployment_config = "cfg1"

    async def get_side_effect(entity_type, name, workspace=None):
        if entity_type is Deployment:
            return deployment_entity
        return sample_config(restart_policy="Always")

    mock_entities.get.side_effect = get_side_effect

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "LOST"


@pytest.mark.asyncio
async def test_read_status_unknown_on_transient_docker_error(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.containers.get.side_effect = APIError("connection reset")

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "UNKNOWN"
    assert "Docker API error" in update.status_message


@pytest.mark.asyncio
async def test_delete_deployment_idempotent(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    update = await docker_backend.delete_deployment("default", "srv")

    assert update.status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_list_managed_deployment_names(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    container = MagicMock()
    container.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
    }
    mock_docker_client.containers.list.return_value = [container]

    names = await docker_backend.list_managed_deployment_names()

    assert names == ["default/srv"]


@pytest.mark.asyncio
async def test_create_volume_bound(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    volume = MagicMock()
    volume.name = "dep-vol-default-data"
    mock_docker_client.volumes.get.side_effect = NotFound("missing")
    mock_docker_client.volumes.create.return_value = volume

    update = await docker_backend.create_volume(
        workspace="default",
        name="data",
        size="1Gi",
        access_modes=["ReadWriteOnce"],
        backend_config={},
    )

    assert update.status == "BOUND"
