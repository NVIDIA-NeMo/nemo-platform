# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AgentRegistration CRUD route tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from nemo_insights_plugin.entities import AgentRegistration
from nemo_platform_plugin.entity_client import NemoEntityConflictError, NemoEntityNotFoundError, NemoPaginationInfo

NOW = datetime.now(timezone.utc)


def stamp(entity):
    entity._id = f"{entity.__entity_type__}-{entity.name}-id"
    entity._created_at = NOW
    entity._updated_at = NOW
    return entity


def list_response(items):
    resp = MagicMock()
    resp.data = items
    resp.pagination = NemoPaginationInfo(
        page=1, page_size=20, current_page_size=len(items), total_pages=1, total_results=len(items)
    )
    return resp


def _make(name: str = "my-agent", workspace: str = "default", **fields) -> AgentRegistration:
    return stamp(AgentRegistration(name=name, workspace=workspace, **fields))


class TestCreate:
    def test_201(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make("my-agent", repo_url="https://example.com/a")
        resp = client.post(
            "/v2/workspaces/default/agent_registrations",
            json={"name": "my-agent", "repo_url": "https://example.com/a"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "my-agent"
        assert body["repo_url"] == "https://example.com/a"

    def test_uploaded_at_set_when_content_provided(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make("a")
        client.post(
            "/v2/workspaces/default/agent_registrations",
            json={"name": "a", "agent_description_content": "# hello"},
        )
        sent = mock_entity_client.create.call_args.args[0]
        assert sent.agent_description_uploaded_at is not None

    def test_uploaded_at_none_when_content_empty(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make("a")
        client.post("/v2/workspaces/default/agent_registrations", json={"name": "a"})
        sent = mock_entity_client.create.call_args.args[0]
        assert sent.agent_description_uploaded_at is None

    def test_409_on_conflict(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.side_effect = NemoEntityConflictError("conflict")
        resp = client.post("/v2/workspaces/default/agent_registrations", json={"name": "dup"})
        assert resp.status_code == 409


class TestGet:
    def test_200(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.return_value = _make("my-agent")
        resp = client.get("/v2/workspaces/default/agent_registrations/my-agent")
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-agent"

    def test_404(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("nope")
        resp = client.get("/v2/workspaces/default/agent_registrations/missing")
        assert resp.status_code == 404


class TestList:
    def test_paginated(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list.return_value = list_response([_make("a"), _make("b")])
        resp = client.get("/v2/workspaces/default/agent_registrations")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total_results"] == 2


class TestUpdate:
    def test_re_upload_content_bumps_uploaded_at(self, client, mock_entity_client: AsyncMock) -> None:
        existing = _make("my-agent")
        existing.agent_description_uploaded_at = None
        mock_entity_client.get.return_value = existing
        mock_entity_client.update.return_value = existing
        resp = client.patch(
            "/v2/workspaces/default/agent_registrations/my-agent",
            json={"agent_description_content": "# new content"},
        )
        assert resp.status_code == 200
        updated_entity = mock_entity_client.update.call_args.args[0]
        assert updated_entity.agent_description_content == "# new content"
        assert updated_entity.agent_description_uploaded_at is not None

    def test_404(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("nope")
        resp = client.patch(
            "/v2/workspaces/default/agent_registrations/missing",
            json={"description": "x"},
        )
        assert resp.status_code == 404


class TestDelete:
    def test_204(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.delete.return_value = None
        resp = client.delete("/v2/workspaces/default/agent_registrations/my-agent")
        assert resp.status_code == 204

    def test_404(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.delete.side_effect = NemoEntityNotFoundError("nope")
        resp = client.delete("/v2/workspaces/default/agent_registrations/missing")
        assert resp.status_code == 404
