# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the example plugin SDK resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_example_plugin.sdk import AsyncExampleClient, ExampleClient
from nemo_example_plugin.types import endpoints
from nemo_example_plugin.types.payloads import (
    CreateExampleItemRequest,
    UpdateExampleItemRequest,
)
from nemo_platform_plugin.client.client import NemoClient

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
    client = ExampleClient(base_url=BASE, workspace=WS, http_client=mock_http)
    return client, mock_http


def _async_client() -> tuple[AsyncExampleClient, AsyncMock]:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    client = AsyncExampleClient(base_url=BASE, workspace=WS, http_client=mock_http)
    return client, mock_http


# ---------------------------------------------------------------------------
# hello — client.method() style
# ---------------------------------------------------------------------------


def test_sync_hello() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, {"message": "Hello, alice!"})
    resp = client.hello(name="alice")
    assert resp.data().message == "Hello, alice!"


@pytest.mark.asyncio
async def test_async_hello() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(200, {"message": "Hello, bob!"})
    resp = await client.hello(name="bob")
    assert resp.data().message == "Hello, bob!"


# ---------------------------------------------------------------------------
# Items CRUD — client.method() style (sync)
# ---------------------------------------------------------------------------


def test_sync_create_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    resp = client.create_item(body=CreateExampleItemRequest(name="my-item", title="My Item"))
    item = resp.data()

    assert item.name == "my-item"
    assert item.title == "My Item"
    mock_http.request.assert_called_once()


def test_sync_create_item_explicit_workspace() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    resp = client.create_item(workspace="other", body=CreateExampleItemRequest(name="my-item", title="My Item"))

    assert resp.data().name == "my-item"
    url_called = mock_http.request.call_args[0][1]
    assert "/workspaces/other/" in url_called


def test_sync_get_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(200, ITEM_PAYLOAD)

    resp = client.get_item(name="my-item")

    assert resp.data().name == "my-item"


def test_sync_list_items() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(
        200, {"data": [ITEM_PAYLOAD], "pagination": None, "sort": None, "filter": None}
    )

    resp = client.list_items()
    page = resp.data()

    assert len(page.items) == 1
    assert page.items[0].name == "my-item"


def test_sync_update_item() -> None:
    client, mock_http = _sync_client()
    updated = {**ITEM_PAYLOAD, "title": "Updated"}
    mock_http.request.return_value = _resp(200, updated)

    resp = client.update_item(name="my-item", body=UpdateExampleItemRequest(title="Updated"))

    assert resp.data().title == "Updated"


def test_sync_delete_item() -> None:
    client, mock_http = _sync_client()
    mock_http.request.return_value = _resp(204)

    client.delete_item(name="my-item")

    mock_http.request.assert_called_once()


# ---------------------------------------------------------------------------
# Low-level: endpoints + client.send() still works
# ---------------------------------------------------------------------------


def test_send_with_endpoint_function() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = _resp(200, {"message": "Hello, alice!"})
    client = NemoClient(base_url=BASE, workspace=WS, http_client=mock_http)

    resp = client.send(endpoints.hello(name="alice"))

    assert resp.data().message == "Hello, alice!"


# ---------------------------------------------------------------------------
# Items CRUD — client.method() style (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_create_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(201, ITEM_PAYLOAD)

    resp = await client.create_item(body=CreateExampleItemRequest(name="my-item", title="My Item"))

    assert resp.data().name == "my-item"


@pytest.mark.asyncio
async def test_async_get_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(200, ITEM_PAYLOAD)

    resp = await client.get_item(name="my-item")

    assert resp.data().name == "my-item"


@pytest.mark.asyncio
async def test_async_list_items() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(
        200, {"data": [ITEM_PAYLOAD], "pagination": None, "sort": None, "filter": None}
    )

    resp = await client.list_items()
    page = resp.data()

    assert len(page.items) == 1
    assert page.items[0].name == "my-item"


@pytest.mark.asyncio
async def test_async_update_item() -> None:
    client, mock_http = _async_client()
    updated = {**ITEM_PAYLOAD, "title": "Updated"}
    mock_http.request.return_value = _resp(200, updated)

    resp = await client.update_item(name="my-item", body=UpdateExampleItemRequest(title="Updated"))

    assert resp.data().title == "Updated"


@pytest.mark.asyncio
async def test_async_delete_item() -> None:
    client, mock_http = _async_client()
    mock_http.request.return_value = _resp(204)

    await client.delete_item(name="my-item")

    mock_http.request.assert_awaited_once()
