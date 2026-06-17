# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import NotRequired
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.response import NemoResponse
from nemo_platform_plugin.client.types import PathParams
from pydantic import BaseModel

BASE = "http://test:8000"


class ItemRequest(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: int
    name: str


class EmptyPath(PathParams):
    pass


class NamePath(PathParams):
    name: str


class WorkspacePath(PathParams):
    workspace: NotRequired[str]


CREATE_ITEM = post("/apis/test/v2/items", path_type=EmptyPath, request_type=ItemRequest, response_type=ItemResponse)
GET_ITEM = get("/apis/test/v2/items/{name}", path_type=NamePath, response_type=ItemResponse)
DELETE_ITEM = delete("/apis/test/v2/items/{name}", path_type=NamePath)
GET_WS_ITEM = get("/apis/test/v2/workspaces/{workspace}/items", path_type=WorkspacePath, response_type=ItemResponse)


class StubClient(NemoClient):
    pass


class AsyncStubClient(AsyncNemoClient):
    pass


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
        content=ItemRequest(name="alice").model_dump_json().encode(),
        headers={"Content-Type": "application/json"},
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
        content=None,
        headers=None,
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


def test_data_success() -> None:
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
