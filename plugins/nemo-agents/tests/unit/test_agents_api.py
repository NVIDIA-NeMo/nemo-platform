# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Agent CRUD route handlers.

Uses FastAPI's TestClient with dependency_overrides to mock EntityClient.
No network or real entity store required.

The test app mounts the agents router at the same prefix as the platform
would: ``/apis/agents``.  This means full URLs match production paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_agents_plugin.api.v2 import agents as agents_router_module
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.entities import Agent, AgentDeployment, DeploymentStatus
from nemo_platform_plugin.entity_client import NemoEntityConflictError, NemoEntityNotFoundError, NemoPaginationInfo

NOW = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    name: str = "calc",
    workspace: str = "default",
    description: str = "",
    config: dict | None = None,
) -> Agent:
    """Return a populated Agent entity (simulates what the entity store returns)."""
    a = Agent(
        name=name,
        workspace=workspace,
        description=description,
        config=config or {},
        config_format="nat-workflow-v1",
    )
    # Simulate fields set by the entity store
    a._id = f"agent-{name}-id"
    a._created_at = NOW
    return a


def _list_response(items: list[Any]) -> MagicMock:
    """Mock the ListResponse returned by EntityClient.list()."""
    resp = MagicMock()
    resp.data = items
    resp.pagination = NemoPaginationInfo(
        page=1,
        page_size=20,
        current_page_size=len(items),
        total_pages=1,
        total_results=len(items),
    )
    return resp


# ---------------------------------------------------------------------------
# Fixture — TestClient with mocked EntityClient
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    """A fully mocked async EntityClient."""
    return AsyncMock()


@pytest.fixture
def test_app(mock_entity_client: AsyncMock) -> FastAPI:
    """FastAPI app with the agents router mounted to match the production path.

    Production: platform mounts at /apis/agents, RouterSpec.prefix adds
    /v2/workspaces/{workspace}.  We replicate both here.
    """
    app = FastAPI()
    app.include_router(
        agents_router_module.router,
        prefix="/apis/agents/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /agents — create
# ---------------------------------------------------------------------------


class TestCreateAgent:
    def test_create_returns_201(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        saved = _make_agent("calc", description="calculator", config={"llms": {}})
        mock_entity_client.create = AsyncMock(return_value=saved)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc", "description": "calculator", "config": {"llms": {}}},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "calc"
        assert body["workspace"] == "default"
        assert body["description"] == "calculator"
        assert body["config"] == {"llms": {}}
        assert body["config_format"] == "nat-workflow-v1"

    def test_create_response_includes_id_and_created_at(
        self, client: TestClient, mock_entity_client: AsyncMock
    ) -> None:
        """Agent entity includes id and created_at as computed fields."""
        saved = _make_agent("calc")
        mock_entity_client.create = AsyncMock(return_value=saved)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc", "config": {}},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "agent-calc-id"
        assert body["created_at"] is not None

    def test_create_calls_entity_client_create(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        saved = _make_agent("calc")
        mock_entity_client.create = AsyncMock(return_value=saved)

        client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc", "config": {}},
        )

        mock_entity_client.create.assert_called_once()
        created_entity: Agent = mock_entity_client.create.call_args[0][0]
        assert created_entity.name == "calc"
        assert created_entity.workspace == "default"

    def test_create_conflict_returns_409(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create = AsyncMock(side_effect=NemoEntityConflictError("already exists"))

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc", "config": {}},
        )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_server_error_returns_500(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create = AsyncMock(side_effect=RuntimeError("db down"))

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc", "config": {}},
        )

        assert resp.status_code == 500

    def test_create_missing_config_returns_422(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Config is required — missing it should be a validation error."""
        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc"},  # no config
        )
        assert resp.status_code == 422

    def test_create_preserves_workspace_from_path(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        saved = _make_agent("calc", workspace="prod")
        mock_entity_client.create = AsyncMock(return_value=saved)

        resp = client.post(
            "/apis/agents/v2/workspaces/prod/agents",
            json={"name": "calc", "config": {}},
        )

        assert resp.status_code == 201
        assert resp.json()["workspace"] == "prod"


# ---------------------------------------------------------------------------
# POST /agents with `url` — create an external agent (pointer to a running one)
# ---------------------------------------------------------------------------


_CARD = {"name": "Ext Agent", "description": "runs elsewhere", "skills": [{"id": "s1", "name": "s1"}]}


class TestCreateExternalAgent:
    def test_url_payload_fetches_card_and_creates_external_agent(
        self, client: TestClient, mock_entity_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agents_router_module, "fetch_agent_card", AsyncMock(return_value=_CARD))
        mock_entity_client.create = AsyncMock(side_effect=lambda a: a)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext", "url": "http://host:10000"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["source"] == "external"
        assert body["endpoint"] == "http://host:10000"
        assert body["card"]["name"] == "Ext Agent"
        # Description falls back to the card when not supplied.
        assert body["description"] == "runs elsewhere"

    def test_explicit_description_overrides_card(
        self, client: TestClient, mock_entity_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agents_router_module, "fetch_agent_card", AsyncMock(return_value=_CARD))
        mock_entity_client.create = AsyncMock(side_effect=lambda a: a)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext", "url": "http://host:10000", "description": "mine"},
        )

        assert resp.status_code == 201
        assert resp.json()["description"] == "mine"

    def test_unreachable_card_returns_502(
        self, client: TestClient, mock_entity_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nemo_agents_plugin.a2a import AgentCardError

        monkeypatch.setattr(
            agents_router_module,
            "fetch_agent_card",
            AsyncMock(side_effect=AgentCardError("could not reach agent")),
        )

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext", "url": "http://host:10000"},
        )

        assert resp.status_code == 502
        assert "could not reach" in resp.json()["detail"]
        mock_entity_client.create.assert_not_called()

    def test_conflict_returns_409(
        self, client: TestClient, mock_entity_client: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agents_router_module, "fetch_agent_card", AsyncMock(return_value=_CARD))
        mock_entity_client.create = AsyncMock(side_effect=NemoEntityConflictError("already exists"))

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext", "url": "http://host:10000"},
        )

        assert resp.status_code == 409

    def test_both_config_and_url_returns_422(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext", "url": "http://host:10000", "config": {"workflow": {}}},
        )
        assert resp.status_code == 422

    def test_neither_config_nor_url_returns_422(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext"},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad_url", ["http://[", "not-a-url", "ftp://host", "http://"])
    def test_malformed_url_returns_422(self, client: TestClient, mock_entity_client: AsyncMock, bad_url: str) -> None:
        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "ext", "url": bad_url},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /agents — list (NemoListResponse envelope)
# ---------------------------------------------------------------------------


class TestListAgents:
    def test_list_returns_200_with_envelope(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """List response is now a NemoListResponse envelope, not a bare array."""
        agents = [_make_agent("a"), _make_agent("b")]
        mock_entity_client.list = AsyncMock(return_value=_list_response(agents))

        resp = client.get("/apis/agents/v2/workspaces/default/agents")

        assert resp.status_code == 200
        body = resp.json()
        # NemoListResponse envelope
        assert set(body.keys()) == {"data", "pagination", "sort", "filter"}
        assert len(body["data"]) == 2
        assert {a["name"] for a in body["data"]} == {"a", "b"}

    def test_list_response_includes_pagination(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_agent("a")]))

        resp = client.get("/apis/agents/v2/workspaces/default/agents")

        assert resp.status_code == 200
        assert resp.json()["pagination"]["total_results"] == 1

    def test_list_data_includes_id_and_created_at(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Each agent entity in data includes id and created_at as computed fields."""
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_agent("calc")]))

        resp = client.get("/apis/agents/v2/workspaces/default/agents")

        item = resp.json()["data"][0]
        assert item["id"] == "agent-calc-id"
        assert item["created_at"] is not None

    def test_list_empty_workspace_returns_empty_data(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))

        resp = client.get("/apis/agents/v2/workspaces/default/agents")

        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_pagination_params_forwarded(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))

        client.get("/apis/agents/v2/workspaces/staging/agents?page=2&page_size=5&sort=name")

        call_kwargs = mock_entity_client.list.call_args.kwargs
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 5
        assert call_kwargs["sort"] == "name"
        assert call_kwargs["workspace"] == "staging"

    def test_list_server_error_returns_500(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(side_effect=RuntimeError("store unavailable"))

        resp = client.get("/apis/agents/v2/workspaces/default/agents")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /agents/{name} — get
# ---------------------------------------------------------------------------


class TestGetAgent:
    def test_get_existing_agent(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(return_value=_make_agent("calc", description="A calculator"))

        resp = client.get("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 200
        assert resp.json()["name"] == "calc"
        assert resp.json()["description"] == "A calculator"
        assert resp.json()["id"] == "agent-calc-id"

    def test_get_not_found_returns_404(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("not found"))

        resp = client.get("/apis/agents/v2/workspaces/default/agents/nonexistent")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_server_error_returns_500(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(side_effect=Exception("connection timeout"))

        resp = client.get("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /agents/{name} — delete
# ---------------------------------------------------------------------------


def _make_deployment(
    name: str = "calc-dep",
    agent: str = "calc",
    workspace: str = "default",
    status: DeploymentStatus = "running",
) -> AgentDeployment:
    return AgentDeployment(name=name, workspace=workspace, agent=agent, status=status)


class TestDeleteAgent:
    def test_delete_existing_returns_204(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        mock_entity_client.delete = AsyncMock(return_value=None)

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 204

    def test_delete_calls_entity_client_delete(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        mock_entity_client.delete = AsyncMock(return_value=None)

        client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        mock_entity_client.delete.assert_called_once_with(Agent, name="calc", workspace="default")

    def test_delete_not_found_returns_404(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        mock_entity_client.delete = AsyncMock(side_effect=NemoEntityNotFoundError("not found"))

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/nonexistent")

        assert resp.status_code == 404

    def test_delete_blocks_on_running_deployment(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """DELETE /agents/{name} returns 409 when a running deployment references the agent."""
        dep = _make_deployment(agent="calc", status="running")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 409
        assert "calc-dep" in resp.json()["detail"]

    def test_delete_blocks_on_pending_deployment(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        dep = _make_deployment(agent="calc", status="pending")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 409

    def test_delete_blocks_on_starting_deployment(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        dep = _make_deployment(agent="calc", status="starting")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 409

    def test_delete_allowed_when_only_failed_deployments(
        self, client: TestClient, mock_entity_client: AsyncMock
    ) -> None:
        """failed deployments do not block deletion — they are terminal."""
        dep = _make_deployment(agent="calc", status="failed")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))
        mock_entity_client.delete = AsyncMock(return_value=None)

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 204

    def test_delete_allowed_when_only_deleting_deployments(
        self, client: TestClient, mock_entity_client: AsyncMock
    ) -> None:
        """deleting deployments do not block — they are already being cleaned up."""
        dep = _make_deployment(agent="calc", status="deleting")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))
        mock_entity_client.delete = AsyncMock(return_value=None)

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 204

    def test_delete_only_checks_deployments_for_this_agent(
        self, client: TestClient, mock_entity_client: AsyncMock
    ) -> None:
        """A running deployment for a *different* agent must not block deletion."""
        other_dep = _make_deployment(name="other-dep", agent="other-agent", status="running")
        mock_entity_client.list = AsyncMock(return_value=_list_response([other_dep]))
        mock_entity_client.delete = AsyncMock(return_value=None)

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 204

    def test_delete_server_error_on_delete_returns_500(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        mock_entity_client.delete = AsyncMock(side_effect=RuntimeError("db error"))

        resp = client.delete("/apis/agents/v2/workspaces/default/agents/calc")

        assert resp.status_code == 500
