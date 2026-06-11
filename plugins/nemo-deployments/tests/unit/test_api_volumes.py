# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import list_response, make_volume
from nemo_deployments_plugin.api.v1 import volumes as volumes_module
from nemo_deployments_plugin.api.v1.dependencies import get_entity_client


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_entity_client: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(
        volumes_module.router,
        prefix="/apis/deployments/v1/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return TestClient(app, raise_server_exceptions=False)


def test_create_volume_201(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.create.return_value = make_volume()
    resp = client.post(
        "/apis/deployments/v1/workspaces/default/volumes",
        json={"name": "vol1", "size": "5Gi"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "PENDING"
    created = mock_entity_client.create.await_args.args[0]
    assert created.name == "vol1"
    assert created.size == "5Gi"
    assert created.workspace == "default"


def test_list_volumes_200(client: TestClient, mock_entity_client: AsyncMock) -> None:
    mock_entity_client.list.return_value = list_response([make_volume()])
    resp = client.get("/apis/deployments/v1/workspaces/default/volumes")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
