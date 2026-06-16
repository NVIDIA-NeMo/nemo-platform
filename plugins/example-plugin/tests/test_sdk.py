# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the example plugin SDK resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_example_plugin.sdk import AsyncExampleClient, ExampleClient

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


def _sync_client() -> tuple[ExampleClient, MagicMock]:
    mock_http = MagicMock(spec=httpx.Client)
    client = ExampleClient(base_url=BASE, http_client=mock_http)
    return client, mock_http


def _async_client() -> tuple[AsyncExampleClient, AsyncMock]:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    client = AsyncExampleClient(base_url=BASE, http_client=mock_http)
    return client, mock_http


# ---------------------------------------------------------------------------
# hello
# ---------------------------------------------------------------------------


def test_sync_hello() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, {"message": "Hello, alice!"})
    assert client.hello("alice") == "Hello, alice!"


@pytest.mark.asyncio
async def test_async_hello() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(200, {"message": "Hello, bob!"})
    assert await client.hello("bob") == "Hello, bob!"


# ---------------------------------------------------------------------------
# Items CRUD — sync
# ---------------------------------------------------------------------------


def test_sync_create_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    item = client.create_item(WS, "my-item", "My Item")

    assert item.name == "my-item"
    assert item.title == "My Item"
    mock_http.request.assert_called_once()
    call_args = mock_http.request.call_args
    assert call_args[0][0] == "POST"
    assert "/v2/workspaces/default/items" in call_args[0][1]


def test_sync_get_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, ITEM_PAYLOAD)

    item = client.get_item(WS, "my-item")

    assert item.name == "my-item"


def test_sync_list_items() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, {"data": [ITEM_PAYLOAD], "pagination": None, "sort": None, "filter": None})

    page = client.list_items(WS)

    assert len(page.data) == 1
    assert page.data[0].name == "my-item"


def test_sync_update_item() -> None:
    client, mock_http = _sync_client()
    updated = {**ITEM_PAYLOAD, "title": "Updated"}
    mock_http.request.return_value = _resp(200, updated)

    item = client.update_item(WS, "my-item", title="Updated")

    assert item.title == "Updated"


def test_sync_delete_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(204)

    client.delete_item(WS, "my-item")

    mock_http.request.assert_called_once()


# ---------------------------------------------------------------------------
# Items CRUD — async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_create_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    item = await client.create_item(WS, "my-item", "My Item")

    assert item.name == "my-item"


@pytest.mark.asyncio
async def test_async_get_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(200, ITEM_PAYLOAD)

    item = await client.get_item(WS, "my-item")

    assert item.name == "my-item"


@pytest.mark.asyncio
async def test_async_delete_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(204)

    await client.delete_item(WS, "my-item")

    mock_http.request.assert_awaited_once()
