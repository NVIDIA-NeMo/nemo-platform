# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the example plugin SDK resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_example_plugin.types.endpoints import (
    CreateItemEndpoint,
    DeleteItemEndpoint,
    GetItemEndpoint,
    HelloEndpoint,
    ListItemsEndpoint,
    UpdateItemEndpoint,
)
from nemo_example_plugin.types.payloads import (
    CreateExampleItemRequest,
    UpdateExampleItemRequest,
)
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

BASE = "http://test:8000"
WS = "default"
ITEM_PAYLOAD = {
    "id": "default/my-item",
    "name": "my-item",
    "workspace": "default",
    "title": "My Item",
    "body": "",
    "tags": [],
    "entity_type": "example_item",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
}


def _resp(status: int, payload=None) -> httpx.Response:
    kwargs: dict = {"request": httpx.Request("GET", BASE)}
    if payload is not None:
        kwargs["json"] = payload
    else:
        kwargs["content"] = b""
    return httpx.Response(status, **kwargs)


def _sync_client() -> tuple[NemoClient, MagicMock]:
    mock_http = MagicMock(spec=httpx.Client)
    client = NemoClient(base_url=BASE, http_client=mock_http)
    return client, mock_http


def _async_client() -> tuple[AsyncNemoClient, AsyncMock]:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    client = AsyncNemoClient(base_url=BASE, http_client=mock_http)
    return client, mock_http


# ---------------------------------------------------------------------------
# hello
# ---------------------------------------------------------------------------


def test_sync_hello() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, {"message": "Hello, alice!"})
    resp = client.call(HelloEndpoint, name="alice")
    assert resp.data().message == "Hello, alice!"


@pytest.mark.asyncio
async def test_async_hello() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(200, {"message": "Hello, bob!"})
    resp = await client.call(HelloEndpoint, name="bob")
    assert resp.data().message == "Hello, bob!"


# ---------------------------------------------------------------------------
# Items CRUD — sync
# ---------------------------------------------------------------------------


def test_sync_create_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    resp = client.call(CreateItemEndpoint, CreateExampleItemRequest(name="my-item", title="My Item"), workspace=WS)
    item = resp.data()

    assert item.name == "my-item"
    assert item.title == "My Item"
    mock_http.request.assert_called_once()


def test_sync_get_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, ITEM_PAYLOAD)

    resp = client.call(GetItemEndpoint, workspace=WS, name="my-item")

    assert resp.data().name == "my-item"


def test_sync_list_items() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(
        200, {"data": [ITEM_PAYLOAD], "pagination": None, "sort": None, "filter": None}
    )

    resp = client.call(ListItemsEndpoint, workspace=WS)
    page = resp.data()

    assert len(page.data) == 1
    assert page.data[0].name == "my-item"


def test_sync_list_items_with_query_params() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(
        200, {"data": [ITEM_PAYLOAD], "pagination": None, "sort": None, "filter": None}
    )

    resp = client.call(ListItemsEndpoint, workspace=WS, query_params={"page": 2, "page_size": 5})
    page = resp.data()

    assert len(page.data) == 1
    _, kwargs = mock_http.request.call_args
    assert kwargs["params"] == {"page": 2, "page_size": 5}


def test_sync_update_item() -> None:
    client, mock_http = _sync_client()
    updated = {**ITEM_PAYLOAD, "title": "Updated"}
    mock_http.request.return_value = _resp(200, updated)

    resp = client.call(UpdateItemEndpoint, UpdateExampleItemRequest(title="Updated"), workspace=WS, name="my-item")

    assert resp.data().title == "Updated"


def test_sync_delete_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(204)

    client.call(DeleteItemEndpoint, workspace=WS, name="my-item")

    mock_http.request.assert_called_once()


# ---------------------------------------------------------------------------
# Items CRUD — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_create_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    resp = await client.call(
        CreateItemEndpoint, CreateExampleItemRequest(name="my-item", title="My Item"), workspace=WS
    )

    assert resp.data().name == "my-item"


@pytest.mark.asyncio
async def test_async_get_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(200, ITEM_PAYLOAD)

    resp = await client.call(GetItemEndpoint, workspace=WS, name="my-item")

    assert resp.data().name == "my-item"


@pytest.mark.asyncio
async def test_async_list_items() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(
        200, {"data": [ITEM_PAYLOAD], "pagination": None, "sort": None, "filter": None}
    )

    resp = await client.call(ListItemsEndpoint, workspace=WS)
    page = resp.data()

    assert len(page.data) == 1
    assert page.data[0].name == "my-item"


@pytest.mark.asyncio
async def test_async_update_item() -> None:
    client, mock_http = _async_client()
    updated = {**ITEM_PAYLOAD, "title": "Updated"}
    mock_http.request.return_value = _resp(200, updated)

    resp = await client.call(
        UpdateItemEndpoint, UpdateExampleItemRequest(title="Updated"), workspace=WS, name="my-item"
    )

    assert resp.data().title == "Updated"


@pytest.mark.asyncio
async def test_async_delete_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(204)

    await client.call(DeleteItemEndpoint, workspace=WS, name="my-item")

    mock_http.request.assert_awaited_once()
