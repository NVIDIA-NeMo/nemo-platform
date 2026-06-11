# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

import pytest
from nemo_deployments_plugin.backends.abc import BackendStatusUpdate, DeploymentBackend
from nemo_deployments_plugin.backends.registry import (
    ExecutorNotFoundError,
    ExecutorRegistry,
    ExecutorSpec,
    UnknownBackendTypeError,
)
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

    async def get_logs(self, **kwargs: Any) -> Any:
        from nemo_deployments_plugin.backends.abc import LogResult

        return LogResult(lines=[])

    async def create_volume(self, **kwargs: Any) -> Any:
        from nemo_deployments_plugin.backends.abc import VolumeStatusUpdate

        return VolumeStatusUpdate(status="PENDING")

    async def read_volume_status(self, **kwargs: Any) -> Any:
        from nemo_deployments_plugin.backends.abc import VolumeStatusUpdate

        return VolumeStatusUpdate(status="BOUND")

    async def delete_volume(self, workspace: str, name: str) -> Any:
        from nemo_deployments_plugin.backends.abc import VolumeStatusUpdate

        return VolumeStatusUpdate(status="RELEASED")


@pytest.fixture
def backend_classes() -> dict[str, type[DeploymentBackend]]:
    return {"docker": _StubBackend, "k8s": _StubBackend}


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


def test_multiple_docker_executors_distinct_config(backend_classes: dict[str, type[DeploymentBackend]]) -> None:
    sdk = AsyncNeMoPlatform(base_url="http://localhost:8080")
    registry = ExecutorRegistry.from_config(
        sdk,
        [
            ExecutorSpec(name="docker-a", backend="docker", config={"port_range_start": 9000}),
            ExecutorSpec(name="docker-b", backend="docker", config={"port_range_start": 9100}),
        ],
        backend_classes=backend_classes,
    )
    a = registry.resolve("docker-a")
    b = registry.resolve("docker-b")
    assert a._config["port_range_start"] == 9000
    assert b._config["port_range_start"] == 9100
