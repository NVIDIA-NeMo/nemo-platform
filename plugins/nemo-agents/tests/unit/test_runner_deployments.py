# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for DeploymentsRunnerBackend compile + lifecycle helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from nemo_agents_plugin.config import AgentsConfig, DeploymentsRunnerConfig
from nemo_agents_plugin.entities import Endpoint
from nemo_agents_plugin.runner.deployments_backend import (
    DeploymentsRunnerBackend,
    build_deployment_config,
    container_gateway_url,
    executor_for_mode,
    map_status,
)
from nemo_deployments_plugin.entities import Deployment, DeploymentConfig
from nemo_deployments_plugin.types import Endpoint as PluginEndpoint
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        ("PENDING", "starting"),
        ("STARTING", "starting"),
        ("READY", "running"),
        ("FAILED", "failed"),
        ("LOST", "failed"),
        ("DELETING", "deleting"),
        ("SUCCEEDED", "failed"),
        ("UNKNOWN", "starting"),
    ],
)
def test_map_status(backend: str, expected: str) -> None:
    assert map_status(backend) == expected


def test_container_gateway_url_rewrites_loopback_for_docker() -> None:
    assert container_gateway_url("http://127.0.0.1:8080", mode="docker") == "http://host.docker.internal:8080"


def test_container_gateway_url_leaves_k8s_unchanged() -> None:
    assert container_gateway_url("http://127.0.0.1:8080", mode="k8s") == "http://127.0.0.1:8080"


def test_container_gateway_url_override_wins() -> None:
    assert (
        container_gateway_url("http://127.0.0.1:8080", mode="docker", override="http://igw:8080/") == "http://igw:8080"
    )


def test_executor_for_mode_prefers_mode_specific() -> None:
    cfg = DeploymentsRunnerConfig(
        default_executor="default-exec",
        docker_executor="docker-exec",
        k8s_executor="k8s-exec",
    )
    assert executor_for_mode(cfg, "docker") == "docker-exec"
    assert executor_for_mode(cfg, "k8s") == "k8s-exec"


def test_build_deployment_config_always_single_container() -> None:
    cfg = build_deployment_config(
        name="hello-dep",
        workspace="default",
        image="nat-runtime:latest",
        port=8000,
        nat_config={"llms": {"nim": {"_type": "nim"}}},
        config_mount_path="/config/agent.yaml",
        mode="docker",
        gateway_base_url="http://host.docker.internal:8080",
    )
    assert cfg.restart_policy == "Always"
    assert len(cfg.containers) == 1
    container = cfg.containers[0]
    assert container.image == "nat-runtime:latest"
    # Docker materializes config from NAT_CONFIG_YAML because config_files are not mounted.
    assert container.command == ["sh", "-c"]
    assert any(e.name == "NAT_CONFIG_YAML" for e in container.env)
    assert container.readiness_probe is not None
    assert cfg.init_containers == []
    assert len(cfg.config_files) == 1
    assert cfg.config_files[0].path == "/config/agent.yaml"
    loaded = yaml.safe_load(cfg.config_files[0].content)
    assert loaded["llms"]["nim"]["_type"] == "nim"


def test_build_deployment_config_k8s_uses_nat_entrypoint() -> None:
    cfg = build_deployment_config(
        name="hello-dep",
        workspace="default",
        image="nat-runtime:latest",
        port=8000,
        nat_config={},
        config_mount_path="/config/agent.yaml",
        mode="k8s",
        gateway_base_url="http://nmp:8080",
    )
    assert cfg.containers[0].command == ["nat", "start", "fastapi"]
    assert "--host" in cfg.containers[0].args and "0.0.0.0" in cfg.containers[0].args
    assert not any(e.name == "NAT_CONFIG_YAML" for e in cfg.containers[0].env)


def test_build_deployment_config_k8s_option_b_when_image_set() -> None:
    cfg = build_deployment_config(
        name="hello-dep",
        workspace="default",
        image="nat-runtime:latest",
        port=8000,
        nat_config={},
        config_mount_path="/config/agent.yaml",
        mode="k8s",
        gateway_base_url="http://nmp:8080",
        plugin_wheels_init_image="busybox:1.36",
    )
    assert len(cfg.init_containers) == 1
    assert cfg.init_containers[0].name == "plugin-wheels"
    assert any(e.name == "PYTHONPATH" for e in cfg.containers[0].env)


def test_build_deployment_config_docker_never_emits_init_containers() -> None:
    cfg = build_deployment_config(
        name="hello-dep",
        workspace="default",
        image="nat-runtime:latest",
        port=8000,
        nat_config={},
        config_mount_path="/config/agent.yaml",
        mode="docker",
        gateway_base_url="http://host.docker.internal:8080",
        plugin_wheels_init_image="busybox:1.36",
    )
    assert cfg.init_containers == []


def _backend(**deployments_kwargs: Any) -> DeploymentsRunnerBackend:
    agents = AgentsConfig(deployments=DeploymentsRunnerConfig(**deployments_kwargs))
    return DeploymentsRunnerBackend(agents)


@pytest.mark.asyncio
async def test_create_deployment_writes_config_and_deployment() -> None:
    backend = _backend(default_image="nat:latest", default_executor="local-docker")
    entities = AsyncMock()
    backend._entities = entities

    with patch("nemo_agents_plugin.runner.deployments_backend.get_base_url", return_value="http://127.0.0.1:8080"):
        info = await backend.create_deployment(
            workspace="default",
            name="hello-dep",
            config={"workflow": {"_type": "react_agent"}},
            port=0,
            deployment_mode="docker",
        )

    assert info.status == "starting"
    assert info.endpoint == ""
    assert entities.create.await_count == 2
    created_config = entities.create.await_args_list[0].args[0]
    created_dep = entities.create.await_args_list[1].args[0]
    assert isinstance(created_config, DeploymentConfig)
    assert isinstance(created_dep, Deployment)
    assert created_config.name == "hello-dep"
    assert created_dep.deployment_config == "hello-dep"
    assert created_dep.executor == "local-docker"
    assert created_dep.desired_state == "READY"


@pytest.mark.asyncio
async def test_create_deployment_missing_image_fails() -> None:
    backend = _backend(default_image="")
    info = await backend.create_deployment(
        workspace="default",
        name="hello-dep",
        config={},
        port=0,
        deployment_mode="docker",
    )
    assert info.status == "failed"
    assert "image" in info.error.lower()


@pytest.mark.asyncio
async def test_create_deployment_cleans_config_on_deployment_failure() -> None:
    backend = _backend(default_image="nat:latest")
    entities = AsyncMock()
    entities.create = AsyncMock(side_effect=[None, RuntimeError("boom")])
    entities.delete = AsyncMock()
    backend._entities = entities

    with (
        patch("nemo_agents_plugin.runner.deployments_backend.get_base_url", return_value="http://127.0.0.1:8080"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await backend.create_deployment(
            workspace="default",
            name="hello-dep",
            config={},
            port=0,
            deployment_mode="docker",
        )

    entities.delete.assert_awaited_once()
    delete_call = entities.delete.await_args
    assert delete_call is not None
    assert delete_call.args[0] is DeploymentConfig


@pytest.mark.asyncio
async def test_get_deployment_status_projects_endpoints() -> None:
    backend = _backend()
    entities = AsyncMock()
    entities.get = AsyncMock(
        return_value=Deployment(
            name="hello-dep",
            workspace="default",
            deployment_config="hello-dep",
            status="READY",
            endpoints=[PluginEndpoint(name="http", url="http://127.0.0.1:32768", protocol="http")],
        )
    )
    backend._entities = entities

    info = await backend.get_deployment_status("default", "hello-dep")
    assert info is not None
    assert info.status == "running"
    assert info.endpoints == [Endpoint(name="http", url="http://127.0.0.1:32768", protocol="http")]
    assert info.endpoint == "http://127.0.0.1:32768"


@pytest.mark.asyncio
async def test_delete_waits_for_deployment_gone_before_config_delete() -> None:
    backend = _backend()
    entities = AsyncMock()
    deployment = Deployment(
        name="hello-dep",
        workspace="default",
        deployment_config="hello-dep",
        status="READY",
    )
    # First get returns the deployment; subsequent gets in the wait loop raise NotFound.
    entities.get = AsyncMock(side_effect=[deployment, NemoEntityNotFoundError("gone")])
    entities.update = AsyncMock()
    entities.delete = AsyncMock()
    backend._entities = entities

    with patch("nemo_agents_plugin.runner.deployments_backend.asyncio.sleep", new_callable=AsyncMock):
        cleaned = await backend.delete_deployment("default", "hello-dep")

    assert cleaned is True
    entities.update.assert_awaited_once()
    assert deployment.status == "DELETING"
    entities.delete.assert_awaited_once()
    delete_call = entities.delete.await_args
    assert delete_call is not None
    assert delete_call.args[0] is DeploymentConfig


@pytest.mark.asyncio
async def test_delete_returns_false_when_deployment_still_present() -> None:
    backend = _backend()
    entities = AsyncMock()
    deployment = Deployment(
        name="hello-dep",
        workspace="default",
        deployment_config="hello-dep",
        status="READY",
    )
    entities.get = AsyncMock(return_value=deployment)
    entities.update = AsyncMock()
    entities.delete = AsyncMock()
    backend._entities = entities

    with patch("nemo_agents_plugin.runner.deployments_backend.asyncio.sleep", new_callable=AsyncMock):
        with patch("nemo_agents_plugin.runner.deployments_backend.time.monotonic", side_effect=[0.0, 0.0, 6.0]):
            cleaned = await backend.delete_deployment("default", "hello-dep")

    assert cleaned is False
    entities.delete.assert_not_called()


def test_agent_deployment_defaults_are_subprocess() -> None:
    from nemo_agents_plugin.entities import AgentDeployment

    dep = AgentDeployment(name="d", workspace="default", agent="a")
    assert dep.deployment_mode == "subprocess"
    assert dep.endpoints == []
    assert dep.image == ""
    assert dep.plugin_deployment == ""
