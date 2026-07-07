# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``DeploymentsRunnerBackend`` — mapping and entity lifecycle.

Covers the pure helpers (status mapping, container gateway URL rewrite,
DeploymentConfig shape) and the backend's translation of the RunnerBackend
interface into nemo-deployments entity operations, using a mocked entity client
so no platform is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_agents_plugin.config import DeploymentsRunnerConfig
from nemo_agents_plugin.runner import deployments_backend as mod
from nemo_agents_plugin.runner.deployments_backend import (
    DeploymentsRunnerBackend,
    build_deployment_config,
    container_gateway_url,
    map_status,
)
from nemo_deployments_plugin.entities import Deployment
from nemo_deployments_plugin.types import Endpoint
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError


def _backend(**deployment_kwargs) -> DeploymentsRunnerBackend:
    cfg = SimpleNamespace(deployments=DeploymentsRunnerConfig(**deployment_kwargs))
    backend = DeploymentsRunnerBackend(cfg)  # type: ignore[arg-type]
    backend._entities = AsyncMock()
    return backend


def test_pure_helpers() -> None:
    """Status map, gateway-URL rewrite, and DeploymentConfig shape."""
    # Status mapping (incl. default fallback).
    assert map_status("READY") == "running"
    assert map_status("PENDING") == "starting"
    assert map_status("FAILED") == "failed"
    assert map_status("DELETING") == "deleting"
    assert map_status("SOMETHING_NEW") == "starting"

    # Loopback rewrite for container reachability; explicit override wins; non-loopback passes through.
    assert container_gateway_url("http://localhost:8080/") == "http://host.docker.internal:8080"
    assert container_gateway_url("http://127.0.0.1:8080") == "http://host.docker.internal:8080"
    assert container_gateway_url("http://localhost:8080", override="http://gw:9/") == "http://gw:9"
    assert container_gateway_url("https://platform.example.com") == "https://platform.example.com"

    # DeploymentConfig compiles to a single container with the expected image/port/env.
    dc = build_deployment_config(
        name="agent-foo",
        workspace="ws",
        image="img:1",
        port=8000,
        env={"NMP_WORKSPACE": "ws"},
    )
    assert dc.name == "agent-foo"
    assert dc.restart_policy == "Always"
    assert len(dc.containers) == 1
    container = dc.containers[0]
    assert container.image == "img:1"
    assert container.ports[0].container_port == 8000
    assert {e.name: e.value for e in container.env} == {"NMP_WORKSPACE": "ws"}


async def test_create_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_deployment writes a prefixed DeploymentConfig + Deployment, injects gateway env."""
    monkeypatch.setattr(mod, "get_base_url", lambda: "http://localhost:8080")
    backend = _backend(executor="local-docker")

    info = await backend.create_deployment("ws", "foo", config={}, port=0, image="img:1")

    assert info.status == "starting"
    assert backend._entities.create.await_count == 2
    created_config, created_deployment = (c.args[0] for c in backend._entities.create.await_args_list)
    assert created_config.name == "agent-foo"  # prefixed to avoid user-deployment collisions
    assert created_deployment.deployment_config == "agent-foo"
    assert created_deployment.executor == "local-docker"
    gateway_env = {e.name: e.value for e in created_config.containers[0].env}["NMP_GATEWAY_BASE_URL"]
    assert gateway_env == "http://host.docker.internal:8080"

    # No image and no default_image → fail fast without touching the entity store.
    backend2 = _backend()
    info2 = await backend2.create_deployment("ws", "foo", config={}, port=0, image=None)
    assert info2.status == "failed"
    backend2._entities.create.assert_not_awaited()


async def test_status_delete_and_list() -> None:
    """get_deployment_status maps status/endpoint; delete tears down; list filters by prefix."""
    backend = _backend()

    ready = Deployment(
        name="agent-foo",
        workspace="ws",
        deployment_config="agent-foo",
        status="READY",
        endpoints=[Endpoint(name="http", url="http://127.0.0.1:9000")],
    )
    backend._entities.get.return_value = ready
    info = await backend.get_deployment_status("ws", "foo")
    assert info is not None
    assert info.status == "running"
    assert info.endpoint == "http://127.0.0.1:9000"

    # Missing entity → None.
    backend._entities.get.side_effect = NemoEntityNotFoundError("nope")
    assert await backend.get_deployment_status("ws", "foo") is None

    # Delete: mark Deployment DELETING (controller removes container + entity) and drop the config.
    backend._entities.get.side_effect = None
    backend._entities.get.return_value = ready
    assert await backend.delete_deployment("ws", "foo") is True
    updated = backend._entities.update.await_args.args[0]
    assert updated.status == "DELETING"
    assert backend._entities.delete.await_count == 1

    # list_deployments returns only our prefixed entities, with the prefix stripped.
    backend._entities.list.return_value = SimpleNamespace(
        data=[
            Deployment(name="agent-foo", workspace="ws", deployment_config="agent-foo", status="READY"),
            Deployment(name="user-thing", workspace="ws", deployment_config="cfg", status="READY"),
        ]
    )
    listed = await backend.list_deployments("ws")
    assert [d.name for d in listed] == ["foo"]
