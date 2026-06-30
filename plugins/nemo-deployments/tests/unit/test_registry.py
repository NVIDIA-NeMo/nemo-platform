# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import NotFound
from nemo_deployments_plugin.backends.base import BackendStatusUpdate, DeploymentBackend, LogResult, VolumeStatusUpdate
from nemo_deployments_plugin.backends.docker.backend import DockerDeploymentBackend
from nemo_deployments_plugin.backends.registry import (
    ExecutorNotFoundError,
    ExecutorRegistry,
    ExecutorSpec,
    UnknownBackendTypeError,
)
from nemo_deployments_plugin.entities import Container, ContainerPort, DeploymentConfig
from nemo_platform import AsyncNeMoPlatform


class _StubBackend(DeploymentBackend):
    def shutdown(self) -> None:
        pass

    async def create_deployment(self, **kwargs: Any) -> BackendStatusUpdate:
        return BackendStatusUpdate(status="PENDING")

    async def read_status(self, **kwargs: Any) -> BackendStatusUpdate:
        return BackendStatusUpdate(status="READY")

    async def delete_deployment(self, workspace: str, name: str) -> BackendStatusUpdate:
        return BackendStatusUpdate(status="DELETING")

    async def list_managed_deployment_names(self) -> list[str]:
        return []

    async def get_logs(self, **kwargs: Any) -> LogResult:
        return LogResult(lines=[])

    async def create_volume(self, **kwargs: Any) -> VolumeStatusUpdate:
        return VolumeStatusUpdate(status="PENDING")

    async def read_volume_status(self, **kwargs: Any) -> VolumeStatusUpdate:
        return VolumeStatusUpdate(status="BOUND")

    async def delete_volume(self, workspace: str, name: str) -> VolumeStatusUpdate:
        return VolumeStatusUpdate(status="RELEASED")


@pytest.fixture
def backend_classes() -> dict[str, type[DeploymentBackend]]:
    return {"docker": _StubBackend, "k8s": _StubBackend}


@contextmanager
def _patched_docker_init(
    *,
    mock_docker_client: MagicMock | None = None,
    mock_entities: AsyncMock | None = None,
) -> Iterator[MagicMock]:
    client = mock_docker_client or MagicMock()
    entities = mock_entities or AsyncMock()
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.AsyncEntitiesResource"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=client),
    ):
        yield client


def test_empty_registry_starts(backend_classes: dict[str, type[DeploymentBackend]]) -> None:
    registry = ExecutorRegistry.empty()
    assert registry.registered_names() == []
    with pytest.raises(ExecutorNotFoundError):
        registry.resolve()


def test_resolve_by_name(backend_classes: dict[str, type[DeploymentBackend]]) -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    registry = ExecutorRegistry.from_config(
        sdk,
        [
            ExecutorSpec(name="local-docker", backend="docker", config={"port_range_start": 9000}),
            ExecutorSpec(name="cluster-a", backend="k8s", config={}),
        ],
        default_executor="local-docker",
        backend_classes=backend_classes,
    )
    assert registry.resolve("cluster-a") is not None
    assert registry.resolve() is registry.resolve("local-docker")


def test_missing_executor_raises(backend_classes: dict[str, type[DeploymentBackend]]) -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    registry = ExecutorRegistry.from_config(
        sdk,
        [ExecutorSpec(name="a", backend="docker", config={})],
        backend_classes=backend_classes,
    )
    with pytest.raises(ExecutorNotFoundError):
        registry.resolve("missing")


def test_unknown_backend_type_raises() -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    with pytest.raises(UnknownBackendTypeError):
        ExecutorRegistry.from_config(
            sdk,
            [ExecutorSpec(name="a", backend="unknown", config={})],
            backend_classes={"docker": _StubBackend},
        )


class _FailingBackend(_StubBackend):
    def init(self) -> None:
        raise RuntimeError("init failed")


def test_registry_rolls_back_on_partial_init(backend_classes: dict[str, type[DeploymentBackend]]) -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    classes = {**backend_classes, "fail": _FailingBackend}
    shutdown_calls: list[str] = []

    class _TrackingStub(_StubBackend):
        def shutdown(self) -> None:
            shutdown_calls.append("shutdown")

    classes["docker"] = _TrackingStub
    with pytest.raises(RuntimeError, match="init failed"):
        ExecutorRegistry.from_config(
            sdk,
            [
                ExecutorSpec(name="ok", backend="docker", config={}),
                ExecutorSpec(name="bad", backend="fail", config={}),
            ],
            backend_classes=classes,
        )
    assert shutdown_calls == ["shutdown"]


def test_multiple_docker_executors_distinct_config() -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    with _patched_docker_init():
        registry = ExecutorRegistry.from_config(
            sdk,
            [
                ExecutorSpec(name="docker-a", backend="docker", config={"port_range_start": 9000}),
                ExecutorSpec(name="docker-b", backend="docker", config={"port_range_start": 9100}),
            ],
        )
    a = registry.resolve("docker-a")
    b = registry.resolve("docker-b")
    assert isinstance(a, DockerDeploymentBackend)
    assert isinstance(b, DockerDeploymentBackend)
    assert a._executor_config.port_range_start == 9000
    assert b._executor_config.port_range_start == 9100


@pytest.mark.asyncio
async def test_executor_port_range_used_for_allocation() -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    mock_entities = AsyncMock()
    mock_docker_client = MagicMock()
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    with (
        _patched_docker_init(mock_docker_client=mock_docker_client, mock_entities=mock_entities),
        patch(
            "nemo_deployments_plugin.backends.docker.backend.find_available_port",
            new_callable=AsyncMock,
            return_value=9055,
        ) as mock_find_port,
    ):
        registry = ExecutorRegistry.from_config(
            sdk,
            [
                ExecutorSpec(
                    name="local-docker",
                    backend="docker",
                    config={"port_range_start": 9050, "port_range_end": 9060, "pull_images": False},
                ),
            ],
        )
        backend = registry.resolve("local-docker")
        assert isinstance(backend, DockerDeploymentBackend)

        mock_entities.get.return_value = DeploymentConfig(
            name="cfg1",
            workspace="default",
            containers=[
                Container(
                    name="main",
                    image="nginx:alpine",
                    ports=[ContainerPort(containerPort=80, protocol="TCP", name="http")],
                )
            ],
        )
        mock_docker_client.containers.run.return_value = MagicMock(id="abc123")

        update = await backend.create_deployment(
            workspace="default",
            name="srv",
            config_name="cfg1",
            labels={},
            backend_config={},
        )

    assert update.status == "STARTING"
    mock_find_port.assert_awaited()
    call_args = mock_find_port.await_args
    assert call_args is not None
    assert call_args.args[1:3] == (9050, 9060)
