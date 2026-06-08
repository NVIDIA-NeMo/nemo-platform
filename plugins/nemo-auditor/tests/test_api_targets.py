# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for AuditTarget CRUD route handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_auditor.api.v2 import targets as targets_router_module
from nemo_auditor.entities import AuditTarget
from nemo_platform_plugin.entity_client import (
    NemoEntityConflictError,
    NemoEntityNotFoundError,
    NemoPaginationInfo,
    get_entity_client,
)

NOW = datetime.now(timezone.utc)


def _make_target(name: str = "tgt-1", workspace: str = "default", **fields) -> AuditTarget:
    fields.setdefault("type", "nim")
    fields.setdefault("model", "meta/llama-3.1-8b-instruct")
    tgt = AuditTarget(name=name, workspace=workspace, **fields)
    tgt._id = f"auditor-audit-target-{name}-id"
    tgt._created_at = NOW
    tgt._updated_at = NOW
    return tgt


def _list_response(items):
    resp = MagicMock()
    resp.data = items
    resp.pagination = NemoPaginationInfo(
        page=1, page_size=20, current_page_size=len(items), total_pages=1, total_results=len(items)
    )
    return resp


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def test_app(mock_entity_client: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(
        targets_router_module.router,
        prefix="/apis/auditor/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


class TestCreateTarget:
    def test_returns_201(self, client, mock_entity_client) -> None:
        mock_entity_client.create = AsyncMock(return_value=_make_target("tgt-1"))
        resp = client.post(
            "/apis/auditor/v2/workspaces/default/targets",
            json={"name": "tgt-1", "type": "nim", "model": "meta/llama-3.1-8b-instruct"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "tgt-1"
        assert body["type"] == "nim"
        assert body["model"] == "meta/llama-3.1-8b-instruct"

    def test_missing_required_model_returns_422(self, client) -> None:
        resp = client.post(
            "/apis/auditor/v2/workspaces/default/targets",
            json={"name": "tgt-1", "type": "nim"},
        )
        assert resp.status_code == 422
        assert any(e["loc"][-1] == "model" for e in resp.json()["detail"])

    def test_missing_required_type_returns_422(self, client) -> None:
        resp = client.post(
            "/apis/auditor/v2/workspaces/default/targets",
            json={"name": "tgt-1", "model": "meta/llama"},
        )
        assert resp.status_code == 422
        assert any(e["loc"][-1] == "type" for e in resp.json()["detail"])

    def test_conflict_returns_409(self, client, mock_entity_client) -> None:
        mock_entity_client.create = AsyncMock(side_effect=NemoEntityConflictError("exists"))
        resp = client.post(
            "/apis/auditor/v2/workspaces/default/targets",
            json={"name": "dup", "type": "nim", "model": "x"},
        )
        assert resp.status_code == 409


class TestGetTarget:
    def test_returns_200(self, client, mock_entity_client) -> None:
        mock_entity_client.get = AsyncMock(return_value=_make_target("tgt-1"))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets/tgt-1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "tgt-1"

    def test_404_when_missing(self, client, mock_entity_client) -> None:
        mock_entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("nope"))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets/missing")
        assert resp.status_code == 404


class TestListTargets:
    def test_returns_pagination(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_target("a"), _make_target("b")]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets")
        assert resp.status_code == 200
        body = resp.json()
        assert [t["name"] for t in body["data"]] == ["a", "b"]
        assert body["pagination"]["total_results"] == 2


class TestUpdateTarget:
    def test_replaces_fields(self, client, mock_entity_client) -> None:
        mock_entity_client.get = AsyncMock(return_value=_make_target("tgt-1", model="old"))
        mock_entity_client.update = AsyncMock(side_effect=lambda t: t)

        resp = client.put(
            "/apis/auditor/v2/workspaces/default/targets/tgt-1",
            json={"type": "nim", "model": "new"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["model"] == "new"

    def test_404_when_missing(self, client, mock_entity_client) -> None:
        mock_entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("nope"))
        resp = client.put(
            "/apis/auditor/v2/workspaces/default/targets/missing",
            json={"type": "nim", "model": "x"},
        )
        assert resp.status_code == 404


class TestDeleteTarget:
    def test_returns_204(self, client, mock_entity_client) -> None:
        mock_entity_client.delete = AsyncMock(return_value=None)
        resp = client.delete("/apis/auditor/v2/workspaces/default/targets/tgt-1")
        assert resp.status_code == 204

    def test_404_when_missing(self, client, mock_entity_client) -> None:
        mock_entity_client.delete = AsyncMock(side_effect=NemoEntityNotFoundError("nope"))
        resp = client.delete("/apis/auditor/v2/workspaces/default/targets/missing")
        assert resp.status_code == 404


class TestListTargetsFiltering:
    def test_filter_by_type_forwards_filter_obj(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_target("a", type="nim")]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets?filter[type]=nim")
        assert resp.status_code == 200, resp.text
        kwargs = mock_entity_client.list.await_args.kwargs
        assert kwargs["filter_obj"] == {"type": "nim"}
        body = resp.json()
        assert body["filter"] == {"type": "nim"}
        assert [t["name"] for t in body["data"]] == ["a"]

    def test_filter_by_model_forwards_filter_obj(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_target("a")]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets?filter[model]=meta/llama-3.1-8b-instruct")
        assert resp.status_code == 200, resp.text
        kwargs = mock_entity_client.list.await_args.kwargs
        assert kwargs["filter_obj"] == {"model": "meta/llama-3.1-8b-instruct"}

    def test_filter_by_description_forwards_filter_obj(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets?filter[description]=prod")
        assert resp.status_code == 200, resp.text
        assert mock_entity_client.list.await_args.kwargs["filter_obj"] == {"description": "prod"}

    def test_filter_by_project_narrows(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets?filter[project]=team-a")
        assert resp.status_code == 200, resp.text
        assert mock_entity_client.list.await_args.kwargs["filter_obj"] == {"project": "team-a"}

    def test_filter_created_at_range_parses_gte_lte(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        resp = client.get(
            "/apis/auditor/v2/workspaces/default/targets"
            "?filter[created_at][$gte]=2024-01-01T00:00:00Z"
            "&filter[created_at][$lte]=2024-12-31T00:00:00Z"
        )
        assert resp.status_code == 200, resp.text
        filter_obj = mock_entity_client.list.await_args.kwargs["filter_obj"]
        assert set(filter_obj["created_at"].keys()) == {"$gte", "$lte"}
        assert filter_obj["created_at"]["$gte"].startswith("2024-01-01")
        assert filter_obj["created_at"]["$lte"].startswith("2024-12-31")

    def test_unknown_filter_key_returns_422(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets?filter[bogus]=x")
        assert resp.status_code == 422

    def test_empty_filter_forwards_none(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_target("a"), _make_target("b")]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets")
        assert resp.status_code == 200, resp.text
        kwargs = mock_entity_client.list.await_args.kwargs
        assert kwargs["filter_obj"] is None
        body = resp.json()
        assert [t["name"] for t in body["data"]] == ["a", "b"]
        assert body["filter"] is None

    def test_response_still_has_data_pagination_sort(self, client, mock_entity_client) -> None:
        mock_entity_client.list = AsyncMock(return_value=_list_response([_make_target("a")]))
        resp = client.get("/apis/auditor/v2/workspaces/default/targets?filter[type]=nim&sort=name")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body
        assert "pagination" in body
        assert body["sort"] == "name"
        assert body["filter"] == {"type": "nim"}
