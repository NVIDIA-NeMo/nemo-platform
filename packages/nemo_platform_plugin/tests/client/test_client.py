# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from typing import TypedDict

from pydantic import BaseModel

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.response import NemoResponse

BASE = "http://test:8000"


class ItemRequest(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: int
    name: str


class EmptyPath(TypedDict):
    pass


class NamePath(TypedDict):
    name: str


class WorkspacePath(TypedDict):
    workspace: str


CREATE_ITEM = post("/v2/items", EmptyPath, ItemRequest, ItemResponse)
GET_ITEM = get("/v2/items/{name}", NamePath, ItemResponse)
DELETE_ITEM = delete("/v2/items/{name}", NamePath)
GET_WS_ITEM = get("/v2/workspaces/{workspace}/items", WorkspacePath, ItemResponse)


class StubClient(NemoClient):
    api_prefix = "/apis/test"


class AsyncStubClient(AsyncNemoClient):
    api_prefix = "/apis/test"


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------


def test_send_post() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "alice"},
    )

    client = StubClient(base_url=BASE, http_client=mock_http)
    resp = client.send(CREATE_ITEM.request(ItemRequest(name="alice")))

    assert isinstance(resp, NemoResponse)
    assert resp.http_response.status_code == 201
    assert resp.body.id == 1
    assert resp.body.name == "alice"

    mock_http.request.assert_called_once_with(
        "POST",
        f"{BASE}/apis/test/v2/items",
        json={"name": "alice"},
    )


def test_send_get_with_path_params() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = StubClient(base_url=BASE, http_client=mock_http)
    resp = client.send(GET_ITEM.request(name="alice"))

    assert resp.body.name == "alice"
    mock_http.request.assert_called_once_with(
        "GET",
        f"{BASE}/apis/test/v2/items/alice",
        json=None,
    )


def test_send_delete() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        204,
        request=httpx.Request("DELETE", f"{BASE}/apis/test/v2/items/alice"),
        content=b"",
    )

    client = StubClient(base_url=BASE, http_client=mock_http)
    resp = client.send(DELETE_ITEM.request(name="alice"))

    assert resp.http_response.status_code == 204
    assert resp.body is None


def test_unwrap_success() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = StubClient(base_url=BASE, http_client=mock_http)
    item = client.send(GET_ITEM.request(name="alice")).data()

    assert item.name == "alice"


def test_base_url_trailing_slash_stripped() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/x"),
        json={"id": 1, "name": "x"},
    )

    client = StubClient(base_url=BASE + "/", http_client=mock_http)
    client.send(GET_ITEM.request(name="x"))

    url_called = mock_http.request.call_args[0][1]
    assert not url_called.startswith(BASE + "//")


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_send_post() -> None:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.request.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "alice"},
    )

    client = AsyncStubClient(base_url=BASE, http_client=mock_http)
    resp = await client.send(CREATE_ITEM.request(ItemRequest(name="alice")))

    assert resp.http_response.status_code == 201
    assert resp.body.name == "alice"


@pytest.mark.asyncio
async def test_async_send_get() -> None:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = AsyncStubClient(base_url=BASE, http_client=mock_http)
    resp = await client.send(GET_ITEM.request(name="alice"))

    assert resp.body.name == "alice"


# ---------------------------------------------------------------------------
# Workspace default
# ---------------------------------------------------------------------------


def test_workspace_default_fills_path() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
        json={"id": 1, "name": "alice"},
    )

    client = StubClient(base_url=BASE, workspace="default", http_client=mock_http)
    client.send(GET_WS_ITEM.request())

    url_called = mock_http.request.call_args[0][1]
    assert "/workspaces/default/" in url_called


def test_workspace_explicit_overrides_default() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/other/items"),
        json={"id": 1, "name": "alice"},
    )

    client = StubClient(base_url=BASE, workspace="default", http_client=mock_http)
    client.send(GET_WS_ITEM.request(workspace="other"))

    url_called = mock_http.request.call_args[0][1]
    assert "/workspaces/other/" in url_called
