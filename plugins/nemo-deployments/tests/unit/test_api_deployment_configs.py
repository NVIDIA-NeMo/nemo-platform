# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import list_response, make_deployment, make_deployment_config
from nemo_deployments_plugin.api.v2 import deployment_configs as configs_module
from nemo_deployments_plugin.api.v2.dependencies import get_entity_client
from nemo_deployments_plugin.entities import Prerequisite
from nemo_platform_plugin.entity_client import NemoEntityConflictError, NemoEntityNotFoundError


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_entity_client: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(
        configs_module.router,
        prefix="/apis/deployments/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return TestClient(app, raise_server_exceptions=False)


def test_create_deployment_config_201(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.list.return_value = list_response([])
    mock_entity_client.create.return_value = make_deployment_config("cfg1")
    resp = client.post(
        "/apis/deployments/v2/workspaces/default/deployment-configs",
        json={"name": "cfg1", "containers": [{"name": "main", "image": "nginx"}]},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "cfg1"


def test_create_deployment_config_cycle_400(client: TestClient, mock_entity_client: AsyncMock) -> None:
    a = make_deployment_config("a")
    b = make_deployment_config("b")
    b.prerequisites = [Prerequisite(deployment_name="a")]
    mock_entity_client.list.return_value = list_response([a, b])
    resp = client.post(
        "/apis/deployments/v2/workspaces/default/deployment-configs",
        json={"name": "a", "prerequisites": [{"deployment_name": "b"}]},
    )
    assert resp.status_code == 400
    assert "cycle" in resp.json()["detail"].lower()


def test_get_deployment_config_404(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.get.side_effect = NemoEntityNotFoundError("missing")
    resp = client.get("/apis/deployments/v2/workspaces/default/deployment-configs/missing")
    assert resp.status_code == 404


def test_delete_deployment_config_204(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.list.return_value = list_response([])
    resp = client.delete("/apis/deployments/v2/workspaces/default/deployment-configs/cfg1")
    assert resp.status_code == 204


def test_delete_deployment_config_409_when_referenced(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.list.return_value = list_response([make_deployment("dep1")])
    resp = client.delete("/apis/deployments/v2/workspaces/default/deployment-configs/cfg1")
    assert resp.status_code == 409
    assert "referenced" in resp.json()["detail"].lower()
    mock_entity_client.delete.assert_not_awaited()


def test_create_deployment_config_409(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.list.return_value = list_response([])
    mock_entity_client.create.side_effect = NemoEntityConflictError("exists")
    resp = client.post(
        "/apis/deployments/v2/workspaces/default/deployment-configs",
        json={"name": "cfg1"},
    )
    assert resp.status_code == 409
