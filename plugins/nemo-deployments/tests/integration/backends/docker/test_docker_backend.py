# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for DockerDeploymentBackend against a real daemon."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker_availability import skip_without_docker
from integration_helpers import force_remove_container
from nemo_deployments_plugin.backends.docker.backend import DockerDeploymentBackend
from nemo_deployments_plugin.backends.labels import container_name
from nemo_deployments_plugin.backends.registry import BACKEND_CLASSES
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import (
    Container,
    ContainerPort,
    Deployment,
    DeploymentConfig,
)

import docker

pytestmark = [
    pytest.mark.skipif("docker" not in BACKEND_CLASSES, reason="Docker backend not registered"),
    skip_without_docker,
]


ALPINE_IMAGE = "alpine:3.20"


def _build_docker_backend(**config_overrides: Any) -> DockerDeploymentBackend:
    mock_entities = AsyncMock()
    mock_sdk = MagicMock()
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.AsyncEntitiesResource"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
    ):
        backend = DockerDeploymentBackend(mock_sdk, {"pull_images": True, **config_overrides})
    backend._entities = mock_entities
    return backend


@pytest.fixture
def docker_backend() -> DockerDeploymentBackend:
    return _build_docker_backend()


def _never_config() -> DeploymentConfig:
    return DeploymentConfig(
        name="echo-cfg",
        workspace="itest",
        restart_policy="Never",  # ty: ignore[unknown-argument]
        containers=[Container(name="main", image=ALPINE_IMAGE, command=["echo"], args=["hello"])],
    )


def _never_sleep_config(*, sleep_seconds: int) -> DeploymentConfig:
    return DeploymentConfig(
        name="sleep-cfg",
        workspace="itest",
        restart_policy="Never",  # ty: ignore[unknown-argument]
        containers=[
            Container(
                name="main",
                image=ALPINE_IMAGE,
                command=["sleep"],
                args=[str(sleep_seconds)],
            )
        ],
    )


def _docker_backend_with_observe_timeout(
    *,
    oneshot_observe_timeout_seconds: int,
) -> DockerDeploymentBackend:
    return _build_docker_backend(oneshot_observe_timeout_seconds=oneshot_observe_timeout_seconds)


def _always_http_config() -> DeploymentConfig:
    return DeploymentConfig(
        name="http-cfg",
        workspace="itest",
        restart_policy="Always",  # ty: ignore[unknown-argument]
        containers=[
            Container(
                name="main",
                image="nginx:alpine",
                ports=[ContainerPort(containerPort=80, protocol="TCP", name="http")],
            )
        ],
    )


@pytest.mark.asyncio
async def test_volume_lifecycle(docker_backend: DockerDeploymentBackend) -> None:
    create = await docker_backend.create_volume(
        workspace="itest",
        name="data",
        size="1Gi",
        access_modes=["ReadWriteOnce"],
        backend_config={},
    )
    assert create.status == "BOUND"

    read = await docker_backend.read_volume_status(workspace="itest", name="data")
    assert read.status == "BOUND"

    deleted = await docker_backend.delete_volume("itest", "data")
    assert deleted.status == "RELEASED"


@pytest.mark.asyncio
async def test_never_deployment_succeeds(docker_backend: DockerDeploymentBackend) -> None:
    config = _never_config()
    docker_backend._entities.get.return_value = config  # ty: ignore[unresolved-attribute]
    c_name = container_name("itest", "echo-job")
    client = docker.from_env()

    try:
        created = await docker_backend.create_deployment(
            workspace="itest",
            name="echo-job",
            config_name="echo-cfg",
            labels={"managed-by": MANAGED_BY_LABEL},
            backend_config={},
        )
        assert created.status == "SUCCEEDED"
        assert created.exit_code == 0

        status = await docker_backend.read_status(workspace="itest", name="echo-job")
        assert status.status == "SUCCEEDED"
        assert status.exit_code == 0
    finally:
        await docker_backend.delete_deployment("itest", "echo-job")
        force_remove_container(client, c_name)


@pytest.mark.asyncio
async def test_never_deployment_outlives_observe_wait_then_succeeds() -> None:
    """Long Never jobs return STARTING on create and finish via read_status polling."""
    job_sleep_seconds = 5
    observe_timeout_seconds = 1
    docker_backend = _docker_backend_with_observe_timeout(
        oneshot_observe_timeout_seconds=observe_timeout_seconds,
    )
    config = _never_sleep_config(sleep_seconds=job_sleep_seconds)
    docker_backend._entities.get.return_value = config  # ty: ignore[unresolved-attribute]
    c_name = container_name("itest", "sleep-job")
    client = docker.from_env()

    try:
        # Warm the image cache so the timed window below measures the observe wait
        # rather than an uncached image pull.
        await asyncio.to_thread(client.images.pull, ALPINE_IMAGE)

        started = time.monotonic()
        created = await docker_backend.create_deployment(
            workspace="itest",
            name="sleep-job",
            config_name="sleep-cfg",
            labels={"managed-by": MANAGED_BY_LABEL},
            backend_config={},
        )
        create_elapsed = time.monotonic() - started

        assert created.status == "STARTING"
        assert "after observe wait" in (created.status_message or "")
        assert create_elapsed < observe_timeout_seconds + 2.0

        deadline = time.monotonic() + 15.0
        status = created
        while time.monotonic() < deadline:
            status = await docker_backend.read_status(workspace="itest", name="sleep-job")
            if status.status in {"SUCCEEDED", "FAILED"}:
                break
            await asyncio.sleep(0.5)

        assert status.status == "SUCCEEDED"
        assert status.exit_code == 0
    finally:
        await docker_backend.delete_deployment("itest", "sleep-job")
        force_remove_container(client, c_name)


@pytest.mark.asyncio
async def test_lost_detection_for_always(docker_backend: DockerDeploymentBackend) -> None:
    deployment = Deployment(name="lost-srv", workspace="itest", deployment_config="http-cfg")
    config = _always_http_config()

    async def get_side_effect(entity_type, name, workspace=None):
        if entity_type is Deployment:
            return deployment
        return config

    docker_backend._entities.get.side_effect = get_side_effect  # ty: ignore[unresolved-attribute]
    c_name = container_name("itest", "lost-srv")
    client = docker.from_env()

    try:
        created = await docker_backend.create_deployment(
            workspace="itest",
            name="lost-srv",
            config_name="http-cfg",
            labels={"managed-by": MANAGED_BY_LABEL},
            backend_config=config.backend_config.model_dump(by_alias=True),
        )
        assert created.status == "STARTING"

        container = client.containers.get(c_name)
        container.remove(force=True)

        status = await docker_backend.read_status(workspace="itest", name="lost-srv")
        assert status.status == "LOST"
    finally:
        await docker_backend.delete_deployment("itest", "lost-srv")
        force_remove_container(client, c_name)
