# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Agent Deployment route handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_agents_plugin.api.v2 import deployments as deployments_router_module
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.entities import NEMO_AGENTS_SPEC_CONFIG_FORMAT, Agent, AgentDeployment

NOW = datetime.now(timezone.utc)


def _fabric_agent_config() -> dict[str, Any]:
    return {
        "config_format": NEMO_AGENTS_SPEC_CONFIG_FORMAT,
        "name": "fabric-agent",
        "description": "Fabric-backed agent",
        "default_harness": "hermes",
        "harnesses": {
            "hermes": {
                "kind": "hermes",
            },
        },
        "models": {
            "default": {
                "provider": "openai",
                "model": "openai/gpt-5.4",
            },
        },
    }


def _make_agent(
    *,
    name: str = "fabric-agent",
    workspace: str = "default",
    config: dict[str, Any] | None = None,
    config_format: str = NEMO_AGENTS_SPEC_CONFIG_FORMAT,
) -> Agent:
    agent = Agent(
        name=name,
        workspace=workspace,
        config=config or _fabric_agent_config(),
        config_format=config_format,
    )
    agent._id = f"agent-{name}-id"
    agent._created_at = NOW
    return agent


def _test_client(mock_entity_client: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(
        deployments_router_module.router,
        prefix="/apis/agents/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return TestClient(app, raise_server_exceptions=False)


class TestCreateDeployment:
    def test_create_preserves_platform_agent_config(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get = AsyncMock(return_value=_make_agent())

        async def _save_deployment(deployment: AgentDeployment) -> AgentDeployment:
            deployment._id = f"deployment-{deployment.name}-id"
            deployment._created_at = NOW
            return deployment

        mock_entity_client.create = AsyncMock(side_effect=_save_deployment)
        client = _test_client(mock_entity_client)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/deployments",
            json={"agent": "fabric-agent", "name": "fabric-dep"},
        )

        assert resp.status_code == 201
        created_deployment: AgentDeployment = mock_entity_client.create.call_args[0][0]
        assert created_deployment.config["config_format"] == NEMO_AGENTS_SPEC_CONFIG_FORMAT
        assert created_deployment.config["environment"]["provider"] == "local"
        assert "functions" not in created_deployment.config
        assert "workflow" not in created_deployment.config

    def test_create_rejects_invalid_platform_agent_config(self) -> None:
        config = _fabric_agent_config()
        config["default_harness"] = "missing"
        mock_entity_client = AsyncMock()
        mock_entity_client.get = AsyncMock(return_value=_make_agent(config=config))
        client = _test_client(mock_entity_client)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/deployments",
            json={"agent": "fabric-agent", "name": "fabric-dep"},
        )

        assert resp.status_code == 400
        assert "Invalid agent config" in resp.json()["detail"]
        mock_entity_client.create.assert_not_called()
