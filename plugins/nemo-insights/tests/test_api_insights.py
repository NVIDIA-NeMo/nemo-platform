# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insight CRUD route tests, including status-transition policy."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from nemo_insights_plugin.entities import Insight, InsightStatus
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


def _make(name: str = "ins-1", workspace: str = "default", **fields) -> Insight:
    fields.setdefault("agent", "my-agent")
    fields.setdefault("description", "d")
    return stamp(Insight(name=name, workspace=workspace, **fields))


class TestCreate:
    def test_201(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make("ins-1")
        resp = client.post(
            "/v2/workspaces/default/insights",
            json={"name": "ins-1", "agent": "my-agent", "description": "d"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "ins-1"
        assert body["status"] == "open"

    def test_409(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.side_effect = NemoEntityConflictError("conflict")
        resp = client.post(
            "/v2/workspaces/default/insights",
            json={"name": "dup", "agent": "my-agent", "description": "d"},
        )
        assert resp.status_code == 409


class TestStatusTransitions:
    @pytest.mark.parametrize(
        "current,requested",
        [
            (InsightStatus.OPEN, "in_progress"),
            (InsightStatus.OPEN, "resolved"),
            (InsightStatus.OPEN, "deleted"),
            (InsightStatus.IN_PROGRESS, "resolved"),
            (InsightStatus.IN_PROGRESS, "open"),
            (InsightStatus.IN_PROGRESS, "deleted"),
            (InsightStatus.RESOLVED, "in_progress"),  # reopening
            (InsightStatus.RESOLVED, "deleted"),
            # idempotent same-state
            (InsightStatus.OPEN, "open"),
            (InsightStatus.RESOLVED, "resolved"),
            (InsightStatus.DELETED, "deleted"),
        ],
    )
    def test_allowed(self, client, mock_entity_client: AsyncMock, current, requested) -> None:
        existing = _make("ins-1", status=current)
        mock_entity_client.get.return_value = existing
        mock_entity_client.update.return_value = existing
        resp = client.patch(
            "/v2/workspaces/default/insights/ins-1",
            json={"status": requested},
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize(
        "current,requested",
        [
            (InsightStatus.RESOLVED, "open"),  # must reopen to in_progress, not open
            (InsightStatus.DELETED, "open"),
            (InsightStatus.DELETED, "in_progress"),
            (InsightStatus.DELETED, "resolved"),
        ],
    )
    def test_disallowed(self, client, mock_entity_client: AsyncMock, current, requested) -> None:
        existing = _make("ins-1", status=current)
        mock_entity_client.get.return_value = existing
        resp = client.patch(
            "/v2/workspaces/default/insights/ins-1",
            json={"status": requested},
        )
        assert resp.status_code == 400


class TestGet:
    def test_200(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.return_value = _make("ins-1")
        resp = client.get("/v2/workspaces/default/insights/ins-1")
        assert resp.status_code == 200

    def test_404(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("nope")
        resp = client.get("/v2/workspaces/default/insights/missing")
        assert resp.status_code == 404


class TestList:
    def test_paginated(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.list.return_value = list_response([_make("a"), _make("b")])
        resp = client.get("/v2/workspaces/default/insights?filter[agent]=my-agent&filter[status]=open")
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["data"]) == 2


class TestSoftDelete:
    def test_delete_sets_status_deleted(self, client, mock_entity_client: AsyncMock) -> None:
        existing = _make("ins-1", status=InsightStatus.OPEN)
        mock_entity_client.get.return_value = existing
        mock_entity_client.update.return_value = existing
        resp = client.delete("/v2/workspaces/default/insights/ins-1")
        assert resp.status_code == 200
        updated = mock_entity_client.update.call_args.args[0]
        assert updated.status == InsightStatus.DELETED

    def test_delete_404(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("nope")
        resp = client.delete("/v2/workspaces/default/insights/missing")
        assert resp.status_code == 404
