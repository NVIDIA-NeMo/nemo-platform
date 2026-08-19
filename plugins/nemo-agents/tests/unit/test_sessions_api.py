# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for AgentSession CRUD and lifecycle routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_agents_plugin.api.v2 import sessions as sessions_router_module
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.entities import AgentDeployment, AgentSession, SessionStatus
from nemo_platform_plugin.entity_client import (
    NemoEntityConflictError,
    NemoEntityNotFoundError,
    NemoPaginationInfo,
)

NOW = datetime.now(timezone.utc)
BASE = "/apis/agents/v2/workspaces/default/sessions"


def _make_deployment(
    *,
    name: str = "fabric-dep",
    workspace: str = "default",
    deployment_id: str = "deployment-id",
) -> AgentDeployment:
    deployment = AgentDeployment(name=name, workspace=workspace, agent="fabric-agent", status="running")
    deployment._id = deployment_id
    deployment._created_at = NOW
    return deployment


def _make_session(
    *,
    name: str = "session-one",
    workspace: str = "default",
    deployment_id: str = "deployment-id",
    status: SessionStatus = SessionStatus.ACTIVE,
) -> AgentSession:
    session = AgentSession(
        name=name,
        workspace=workspace,
        deployment_id=deployment_id,
        status=status,
    )
    session._id = f"session-{name}-id"
    session._created_at = NOW
    return session


def _list_response(*sessions: AgentSession) -> MagicMock:
    response = MagicMock()
    response.data = list(sessions)
    response.pagination = NemoPaginationInfo(
        page=1,
        page_size=20,
        current_page_size=len(sessions),
        total_pages=1,
        total_results=len(sessions),
    )
    return response


def _test_client(mock_entity_client: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(
        sessions_router_module.router,
        prefix="/apis/agents/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return TestClient(app, raise_server_exceptions=False)


class TestCreateSession:
    def test_create_for_deployment(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.find_one.return_value = _make_deployment()

        async def _save(session: AgentSession) -> AgentSession:
            session._id = "session-id"
            session._created_at = NOW
            return session

        mock_entity_client.create.side_effect = _save
        client = _test_client(mock_entity_client)

        response = client.post(BASE, json={"deployment_id": "deployment-id", "name": "session-one"})

        assert response.status_code == 201
        assert response.json()["id"] == "session-id"
        assert response.json()["name"] == "session-one"
        assert response.json()["deployment_id"] == "deployment-id"
        assert response.json()["status"] == "active"
        mock_entity_client.find_one.assert_awaited_once_with(
            AgentDeployment,
            workspace="default",
            filter_obj={"id": "deployment-id"},
        )

    def test_create_generates_name_from_deployment(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.find_one.return_value = _make_deployment(name="fabric-dep")

        async def _save(session: AgentSession) -> AgentSession:
            session._id = "session-id"
            session._created_at = NOW
            return session

        mock_entity_client.create.side_effect = _save
        client = _test_client(mock_entity_client)

        with patch.object(sessions_router_module.secrets, "token_hex", return_value="a1b2c3d4"):
            response = client.post(BASE, json={"deployment_id": "deployment-id"})

        assert response.status_code == 201
        assert response.json()["name"] == "fabric-dep-a1b2c3d4"

    def test_create_requires_deployment_id(self) -> None:
        mock_entity_client = AsyncMock()
        client = _test_client(mock_entity_client)

        response = client.post(BASE, json={"name": "session-one"})

        assert response.status_code == 422
        mock_entity_client.find_one.assert_not_awaited()

    def test_create_returns_404_for_unknown_deployment(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.find_one.side_effect = NemoEntityNotFoundError("not found")
        client = _test_client(mock_entity_client)

        response = client.post(BASE, json={"deployment_id": "missing"})

        assert response.status_code == 404
        assert response.json()["detail"] == "Deployment ID 'missing' not found in workspace 'default'."
        mock_entity_client.create.assert_not_awaited()

    def test_create_returns_404_for_cross_workspace_deployment(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.find_one.return_value = _make_deployment(workspace="other")
        client = _test_client(mock_entity_client)

        response = client.post(BASE, json={"deployment_id": "deployment-id"})

        assert response.status_code == 404
        mock_entity_client.create.assert_not_awaited()

    def test_create_returns_409_for_duplicate_name(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.find_one.return_value = _make_deployment()
        mock_entity_client.create.side_effect = NemoEntityConflictError("exists")
        client = _test_client(mock_entity_client)

        response = client.post(BASE, json={"deployment_id": "deployment-id", "name": "session-one"})

        assert response.status_code == 409


class TestListSessions:
    def test_list_sessions(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.list.return_value = _list_response(_make_session())
        client = _test_client(mock_entity_client)

        response = client.get(BASE)

        assert response.status_code == 200
        assert response.json()["data"][0]["name"] == "session-one"
        assert response.json()["pagination"]["total_results"] == 1
        assert mock_entity_client.list.await_args.kwargs["filter_obj"] is None

    def test_list_filters_by_deployment_id(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.list.return_value = _list_response(_make_session())
        client = _test_client(mock_entity_client)

        response = client.get(f"{BASE}?filter[deployment_id]=deployment-id")

        assert response.status_code == 200
        assert mock_entity_client.list.await_args.kwargs["filter_obj"] == {"deployment_id": "deployment-id"}

    def test_list_rejects_unknown_filter(self) -> None:
        mock_entity_client = AsyncMock()
        client = _test_client(mock_entity_client)

        response = client.get(f"{BASE}?filter[unknown]=value")

        assert response.status_code == 422
        mock_entity_client.list.assert_not_awaited()


class TestGetSession:
    def test_get_by_name(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.return_value = _make_session()
        client = _test_client(mock_entity_client)

        response = client.get(f"{BASE}/session-one")

        assert response.status_code == 200
        assert response.json()["name"] == "session-one"
        mock_entity_client.get.assert_awaited_once_with(AgentSession, name="session-one", workspace="default")

    def test_get_returns_404(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("not found")
        client = _test_client(mock_entity_client)

        response = client.get(f"{BASE}/missing")

        assert response.status_code == 404


class TestCloseSession:
    def test_close_active_session(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.return_value = _make_session()
        mock_entity_client.update.side_effect = lambda session: session
        client = _test_client(mock_entity_client)

        with patch.object(sessions_router_module, "_cleanup_fabric_runtime", new_callable=AsyncMock) as cleanup:
            response = client.post(f"{BASE}/session-one/close")

        assert response.status_code == 200
        assert response.json()["status"] == "closed"
        updated: AgentSession = mock_entity_client.update.await_args.args[0]
        assert updated.status is SessionStatus.CLOSED
        cleanup.assert_awaited_once_with(mock_entity_client, updated)

    def test_close_is_idempotent(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.return_value = _make_session(status=SessionStatus.CLOSED)
        client = _test_client(mock_entity_client)

        with patch.object(sessions_router_module, "_cleanup_fabric_runtime", new_callable=AsyncMock) as cleanup:
            response = client.post(f"{BASE}/session-one/close")

        assert response.status_code == 200
        assert response.json()["status"] == "closed"
        mock_entity_client.update.assert_not_awaited()
        cleanup.assert_awaited_once_with(mock_entity_client, mock_entity_client.get.return_value)

    def test_close_returns_404(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("not found")
        client = _test_client(mock_entity_client)

        response = client.post(f"{BASE}/missing/close")

        assert response.status_code == 404

    def test_close_returns_409_for_concurrent_update(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.return_value = _make_session()
        mock_entity_client.update.side_effect = NemoEntityConflictError("conflict")
        client = _test_client(mock_entity_client)

        response = client.post(f"{BASE}/session-one/close")

        assert response.status_code == 409


class TestDeleteSession:
    def test_delete_session(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.return_value = _make_session()
        client = _test_client(mock_entity_client)

        with patch.object(sessions_router_module, "_cleanup_fabric_runtime", new_callable=AsyncMock) as cleanup:
            response = client.delete(f"{BASE}/session-one")

        assert response.status_code == 204
        mock_entity_client.get.assert_awaited_once_with(AgentSession, name="session-one", workspace="default")
        mock_entity_client.delete.assert_awaited_once_with(AgentSession, name="session-one", workspace="default")
        cleanup.assert_awaited_once_with(mock_entity_client, mock_entity_client.get.return_value)

    def test_delete_returns_404(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("not found")
        client = _test_client(mock_entity_client)

        response = client.delete(f"{BASE}/missing")

        assert response.status_code == 404
        mock_entity_client.delete.assert_not_awaited()

    def test_delete_returns_409_for_concurrent_update(self) -> None:
        mock_entity_client = AsyncMock()
        mock_entity_client.get.return_value = _make_session()
        mock_entity_client.delete.side_effect = NemoEntityConflictError("conflict")
        client = _test_client(mock_entity_client)

        response = client.delete(f"{BASE}/session-one")

        assert response.status_code == 409


class TestFabricRuntimeCleanup:
    async def test_cleanup_calls_bound_deployment_session_endpoint(self) -> None:
        mock_entity_client = AsyncMock()
        deployment = _make_deployment()
        deployment.endpoint = "http://localhost:9001"
        mock_entity_client.find_one.return_value = deployment
        session = _make_session(name="session/one")
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204)

        cleanup_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.object(sessions_router_module.httpx, "AsyncClient", return_value=cleanup_client):
            await sessions_router_module._cleanup_fabric_runtime(mock_entity_client, session)

        assert len(requests) == 1
        assert requests[0].method == "DELETE"
        assert str(requests[0].url) == "http://localhost:9001/v1/sessions/session-session%2Fone-id"

    async def test_cleanup_ignores_missing_runtime(self) -> None:
        mock_entity_client = AsyncMock()
        deployment = _make_deployment()
        deployment.endpoint = "http://localhost:9001"
        mock_entity_client.find_one.return_value = deployment
        session = _make_session()

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        cleanup_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.object(sessions_router_module.httpx, "AsyncClient", return_value=cleanup_client):
            await sessions_router_module._cleanup_fabric_runtime(mock_entity_client, session)

    async def test_cleanup_ignores_connection_failure(self) -> None:
        mock_entity_client = AsyncMock()
        deployment = _make_deployment()
        deployment.endpoint = "http://localhost:9001"
        mock_entity_client.find_one.return_value = deployment
        session = _make_session()

        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        cleanup_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.object(sessions_router_module.httpx, "AsyncClient", return_value=cleanup_client):
            await sessions_router_module._cleanup_fabric_runtime(mock_entity_client, session)
