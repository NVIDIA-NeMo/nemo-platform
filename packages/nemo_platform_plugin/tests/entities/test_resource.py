# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Behavioral tests for EntityStoreResource (NemoClient-backed entity client)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from nemo_platform_plugin.entities import (
    EntityBase,
    EntityConflictError,
    EntityNotFoundError,
    EntityStoreResource,
    EntityValidationError,
)

BASE = "http://test:8000"


class Widget(EntityBase):
    __entity_type__ = "widget"
    colour: str = "red"
    size: int = 1


def _entity_json(
    *,
    name: str = "w1",
    workspace: str = "default",
    data: dict[str, Any] | None = None,
    db_version: int = 1,
    entity_id: str = "widget-abc",
    parent: str | None = None,
) -> dict[str, Any]:
    return {
        "entity_type": "widget",
        "id": entity_id,
        "workspace": workspace,
        "parent": parent,
        "project": None,
        "name": name,
        "data": data if data is not None else {"colour": "blue", "size": 3},
        "created_at": "2026-01-01T00:00:00Z",
        "created_by": "user:alice",
        "updated_at": "2026-01-02T00:00:00Z",
        "updated_by": "user:bob",
        "db_version": db_version,
    }


def _resp(body: dict[str, Any], status: int = 200, method: str = "GET") -> httpx.Response:
    return httpx.Response(status, request=httpx.Request(method, f"{BASE}/x"), json=body)


def _page(items: list[dict[str, Any]], *, page: int = 1, total_pages: int = 1, page_size: int = 100) -> dict[str, Any]:
    return {
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "current_page_size": len(items),
            "total_pages": total_pages,
            "total_results": total_pages * page_size,
        },
    }


def _client(mock_http: AsyncMock, workspace: str | None = "default") -> EntityStoreResource:
    from nemo_platform_plugin.entities.client import AsyncEntitiesClient

    return EntityStoreResource(AsyncEntitiesClient(base_url=BASE, workspace=workspace, http_client=mock_http))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCrud:
    @pytest.mark.asyncio
    async def test_create(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json(data={"colour": "green", "size": 5}), method="POST")

        client = _client(mock_http)
        result = await client.create(Widget(name="w1", workspace="default", colour="green", size=5))

        assert isinstance(result, Widget)
        assert result.colour == "green"
        assert result.size == 5
        assert result.id == "widget-abc"
        assert result.db_version == 1

        call = mock_http.request.call_args
        assert call.args[0] == "POST"
        assert call.args[1].endswith("/apis/entities/v2/workspaces/default/entities/widget")
        sent = json.loads(call.kwargs["content"])
        assert sent["name"] == "w1"
        assert sent["data"] == {"colour": "green", "size": 5}

    @pytest.mark.asyncio
    async def test_get(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json())

        client = _client(mock_http)
        result = await client.get(Widget, "w1")

        assert result.name == "w1"
        assert result.colour == "blue"
        url = mock_http.request.call_args.args[1]
        assert url.endswith("/apis/entities/v2/workspaces/default/entities/widget/w1")

    @pytest.mark.asyncio
    async def test_get_workspace_qualified_name(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json(workspace="prod"))

        client = _client(mock_http)
        await client.get(Widget, "prod/w1")

        url = mock_http.request.call_args.args[1]
        assert "/workspaces/prod/entities/widget/w1" in url

    @pytest.mark.asyncio
    async def test_get_by_id(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json())

        client = _client(mock_http)
        result = await client.get_by_id(Widget, "widget-abc")

        assert result.id == "widget-abc"
        assert mock_http.request.call_args.args[1].endswith("/apis/entities/v2/entities/widget-abc")

    @pytest.mark.asyncio
    async def test_update_sends_expected_db_version(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json(db_version=2), method="PUT")

        client = _client(mock_http)
        widget = Widget(name="w1", workspace="default")
        widget._db_version = 1
        result = await client.update(widget)

        assert result.db_version == 2
        sent = json.loads(mock_http.request.call_args.kwargs["content"])
        assert sent["expected_db_version"] == 1
        assert "new_name" not in sent  # not renaming

    @pytest.mark.asyncio
    async def test_update_rename(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json(name="w2"), method="PUT")

        client = _client(mock_http)
        widget = Widget(name="w2", workspace="default")
        await client.update(widget, original_name="w1")

        url = mock_http.request.call_args.args[1]
        assert url.endswith("/entities/widget/w1")  # path uses original name
        sent = json.loads(mock_http.request.call_args.kwargs["content"])
        assert sent["new_name"] == "w2"

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(
            {"message": "ok", "id": "default/widget/w1", "deleted_count": 1}, method="DELETE"
        )

        client = _client(mock_http)
        result = await client.delete(Widget, "w1")

        assert result.deleted_count == 1
        assert mock_http.request.call_args.args[0] == "DELETE"


# ---------------------------------------------------------------------------
# Listing / pagination
# ---------------------------------------------------------------------------


class TestList:
    @pytest.mark.asyncio
    async def test_list_single_page(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(
            _page([_entity_json(name="w1"), _entity_json(name="w2")], page=1, total_pages=1)
        )

        client = _client(mock_http)
        result = await client.list(Widget, workspace="default")
        page = result.page()

        assert [w.name for w in page.items] == ["w1", "w2"]
        assert all(isinstance(w, Widget) for w in page.items)
        assert page.total_pages == 1

    @pytest.mark.asyncio
    async def test_list_items_across_pages(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.side_effect = [
            _resp(_page([_entity_json(name="w1")], page=1, total_pages=2, page_size=1)),
            _resp(_page([_entity_json(name="w2")], page=2, total_pages=2, page_size=1)),
        ]

        client = _client(mock_http)
        result = await client.list(Widget, workspace="default", page_size=1)
        names = [w.name async for w in result.items()]

        assert names == ["w1", "w2"]

    @pytest.mark.asyncio
    async def test_list_filter_operation_and_str_mutually_exclusive(self) -> None:
        from nemo_platform_plugin.filter_ops import ComparisonOperation, FilterOperator

        client = _client(AsyncMock(spec=httpx.AsyncClient))
        op = ComparisonOperation(field="colour", operator=FilterOperator.EQ, value="blue")
        with pytest.raises(ValueError, match="not both"):
            await client.list(Widget, filter_operation=op, filter_str="{}")

    @pytest.mark.asyncio
    async def test_list_sort_prefixes_data_field(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_page([], page=1, total_pages=1))

        client = _client(mock_http)
        result = await client.list(Widget, workspace="default", sort="colour")
        result.page()

        params = mock_http.request.call_args.kwargs["params"]
        # colour is not a base field → prefixed with data.
        assert params["sort"] == "data.colour"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_create_conflict(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp({"detail": "exists"}, status=409, method="POST")

        client = _client(mock_http)
        with pytest.raises(EntityConflictError):
            await client.create(Widget(name="w1", workspace="default"))

    @pytest.mark.asyncio
    async def test_get_not_found(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp({"detail": "nope"}, status=404)

        client = _client(mock_http)
        with pytest.raises(EntityNotFoundError):
            await client.get(Widget, "missing")

    @pytest.mark.asyncio
    async def test_create_validation_error(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp({"detail": "bad project"}, status=422, method="POST")

        client = _client(mock_http)
        with pytest.raises(EntityValidationError, match="bad project"):
            await client.create(Widget(name="w1", workspace="default"))

    @pytest.mark.asyncio
    async def test_update_version_conflict(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp({"detail": "version mismatch"}, status=409, method="PUT")

        client = _client(mock_http)
        widget = Widget(name="w1", workspace="default")
        with pytest.raises(EntityConflictError):
            await client.update(widget)


# ---------------------------------------------------------------------------
# as_service
# ---------------------------------------------------------------------------


class TestAsService:
    @pytest.mark.asyncio
    async def test_as_service_sets_principal_header(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json())

        base = _client(mock_http)
        svc = base.as_service("auth")
        await svc.get(Widget, "w1")

        headers = mock_http.request.call_args.kwargs["headers"]
        assert headers["X-NMP-Principal-Id"] == "service:auth"
        assert "X-NMP-Internal" not in headers

    @pytest.mark.asyncio
    async def test_as_service_internal(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _resp(_entity_json())

        svc = _client(mock_http).as_service("auth", internal=True)
        await svc.get(Widget, "w1")

        headers = mock_http.request.call_args.kwargs["headers"]
        assert headers["X-NMP-Principal-Id"] == "service:auth"
        assert headers["X-NMP-Internal"] == "true"

    def test_as_service_does_not_mutate_original(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        base = _client(mock_http)
        base.as_service("auth")
        assert "X-NMP-Principal-Id" not in base._client._default_headers


# ---------------------------------------------------------------------------
# DI provider default implementation
# ---------------------------------------------------------------------------


class TestGetEntityStoreResourceDefault:
    def test_builds_env_scoped_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_platform_plugin.dependencies import get_entity_store_resource

        monkeypatch.setenv("NMP_BASE_URL", "http://localhost:9999")
        monkeypatch.setenv("NMP_PRINCIPAL", json.dumps({"id": "user:alice", "email": "a@x.com"}))

        client = get_entity_store_resource()

        assert isinstance(client, EntityStoreResource)
        assert client._client.base_url == "http://localhost:9999"
        assert client._client._default_headers["X-NMP-Principal-Id"] == "user:alice"

    def test_defaults_without_principal_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_platform_plugin.dependencies import get_entity_store_resource

        monkeypatch.delenv("NMP_BASE_URL", raising=False)
        monkeypatch.delenv("NMP_PRINCIPAL", raising=False)

        client = get_entity_store_resource()

        assert isinstance(client, EntityStoreResource)
        assert client._client.base_url == "http://localhost:8080"
        assert "X-NMP-Principal-Id" not in client._client._default_headers
