# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for deployment create route (external-agent guard + happy path).

Uses FastAPI TestClient with a mocked EntityClient; no network or entity store.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_agents_plugin.api.v2 import deployments as deployments_router_module
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.entities import Agent


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_entity_client: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(
        deployments_router_module.router,
        prefix="/apis/agents/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return TestClient(app, raise_server_exceptions=False)


def test_deploy_external_agent_returns_400(client: TestClient, mock_entity_client: AsyncMock) -> None:
    external = Agent(name="ext", workspace="default", source="external", endpoint="http://host:10000")
    mock_entity_client.get = AsyncMock(return_value=external)

    resp = client.post(
        "/apis/agents/v2/workspaces/default/deployments",
        json={"agent": "ext"},
    )

    assert resp.status_code == 400
    assert "external" in resp.json()["detail"].lower()
    mock_entity_client.create.assert_not_called()


def test_deploy_managed_agent_creates_pending(client: TestClient, mock_entity_client: AsyncMock) -> None:
    managed = Agent(name="calc", workspace="default", config={"workflow": {"_type": "react_agent"}})
    mock_entity_client.get = AsyncMock(return_value=managed)
    mock_entity_client.create = AsyncMock(side_effect=lambda d: d)

    resp = client.post(
        "/apis/agents/v2/workspaces/default/deployments",
        json={"agent": "calc"},
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    mock_entity_client.create.assert_called_once()
