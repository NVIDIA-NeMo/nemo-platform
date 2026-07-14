# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient, _type_adapter
from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.errors import NemoHTTPError, NemoResponseValidationError, NotFoundError
from nemo_platform_plugin.client.response import NemoResponse
from pydantic import BaseModel

BASE = "http://test:8000"


class ItemRequest(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: int
    name: str


def test_response_type_adapters_are_cached() -> None:
    _type_adapter.cache_clear()

    first = _type_adapter(ItemResponse)
    second = _type_adapter(ItemResponse)

    assert first is second
    assert _type_adapter.cache_info().misses == 1


@post("/apis/test/v2/items")
def CREATE_ITEM(body: ItemRequest) -> ItemResponse:
    raise NotImplementedError


@get("/apis/test/v2/items/{name}")
def GET_ITEM(*, name: str) -> ItemResponse:
    raise NotImplementedError


@delete("/apis/test/v2/items/{name}")
def DELETE_ITEM(*, name: str) -> None:
    raise NotImplementedError


@get("/apis/test/v2/workspaces/{workspace}/items")
def GET_WS_ITEM(*, workspace: str | None = None) -> ItemResponse:
    raise NotImplementedError


@get("/apis/test/v2/items")
def GET_ITEMS_WITH_PARAMS(*, query_params: dict | None = None) -> ItemResponse:
    raise NotImplementedError


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

    client = NemoClient(base_url=BASE, http_client=mock_http)
    resp = client.send(CREATE_ITEM(ItemRequest(name="alice")))

    assert isinstance(resp, NemoResponse)
    assert resp.http_response.status_code == 201
    assert resp.body.id == 1
    assert resp.body.name == "alice"

    mock_http.request.assert_called_once_with(
        "POST",
        f"{BASE}/apis/test/v2/items",
        content=ItemRequest(name="alice").model_dump_json().encode(),
        headers={"Content-Type": "application/json"},
        params=None,
    )


def test_send_get_with_path_params() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    resp = client.send(GET_ITEM(name="alice"))

    assert resp.body.name == "alice"
    mock_http.request.assert_called_once_with(
        "GET",
        f"{BASE}/apis/test/v2/items/alice",
        content=None,
        headers=None,
        params=None,
    )


def test_send_url_encodes_path_params() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/name%20with%20%3F%23%2F"),
        json={"id": 1, "name": "encoded"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(GET_ITEM(name="name with ?#/"))

    assert mock_http.request.call_args.args[1] == f"{BASE}/apis/test/v2/items/name%20with%20%3F%23%2F"


def test_send_url_encodes_default_workspace() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/team%20one%2Fwest/items"),
        json={"id": 1, "name": "encoded"},
    )

    client = NemoClient(base_url=BASE, workspace="team one/west", http_client=mock_http)
    client.send(GET_WS_ITEM())

    assert mock_http.request.call_args.args[1] == f"{BASE}/apis/test/v2/workspaces/team%20one%2Fwest/items"


def test_send_delete() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        204,
        request=httpx.Request("DELETE", f"{BASE}/apis/test/v2/items/alice"),
        content=b"",
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    resp = client.send(DELETE_ITEM(name="alice"))

    assert resp.http_response.status_code == 204
    assert resp.body is None


def test_data_success() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    item = client.send(GET_ITEM(name="alice")).data()

    assert item.name == "alice"


def test_base_url_trailing_slash_stripped() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/x"),
        json={"id": 1, "name": "x"},
    )

    client = NemoClient(base_url=BASE + "/", http_client=mock_http)
    client.send(GET_ITEM(name="x"))

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

    client = AsyncNemoClient(base_url=BASE, http_client=mock_http)
    resp = await client.send(CREATE_ITEM(ItemRequest(name="alice")))

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

    client = AsyncNemoClient(base_url=BASE, http_client=mock_http)
    resp = await client.send(GET_ITEM(name="alice"))

    assert resp.body.name == "alice"


# ---------------------------------------------------------------------------
# Workspace default
# ---------------------------------------------------------------------------


def test_workspace_explicit_in_request() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
    client.send(GET_WS_ITEM(workspace="default"))

    url_called = mock_http.request.call_args[0][1]
    assert "/workspaces/default/" in url_called


def test_workspace_default_fills_omitted_path_param() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
    # workspace omitted — client default fills it
    client.send(GET_WS_ITEM())

    url_called = mock_http.request.call_args[0][1]
    assert "/workspaces/default/" in url_called


def test_workspace_explicit_overrides_default() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/other/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
    client.send(GET_WS_ITEM(workspace="other"))

    url_called = mock_http.request.call_args[0][1]
    assert "/workspaces/other/" in url_called


# ---------------------------------------------------------------------------
# Query params
# ---------------------------------------------------------------------------


def test_query_params_passed_to_httpx() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(GET_ITEMS_WITH_PARAMS(query_params={"page": 2, "page_size": 10}))

    mock_http.request.assert_called_once_with(
        "GET",
        f"{BASE}/apis/test/v2/items",
        content=None,
        headers=None,
        params={"page": 2, "page_size": 10},
    )


def test_query_params_none_values_filtered() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(GET_ITEMS_WITH_PARAMS(query_params={"page_cursor": None, "page_size": 10}))

    mock_http.request.assert_called_once_with(
        "GET",
        f"{BASE}/apis/test/v2/items",
        content=None,
        headers=None,
        params={"page_size": 10},
    )


def test_query_params_all_none_becomes_none() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(GET_ITEMS_WITH_PARAMS(query_params={"page_cursor": None}))

    mock_http.request.assert_called_once_with(
        "GET",
        f"{BASE}/apis/test/v2/items",
        content=None,
        headers=None,
        params=None,
    )


# ---------------------------------------------------------------------------
# Error response body parsing
# ---------------------------------------------------------------------------


def test_error_response_extracts_detail() -> None:
    """send() raises NemoHTTPError with detail extracted from response body."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        422,
        request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
        json={"detail": "Validation failed: name is required"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)

    with pytest.raises(NemoHTTPError) as exc_info:
        client.send(CREATE_ITEM(ItemRequest(name="")))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Validation failed: name is required"
    assert "422" in str(exc_info.value)
    assert "Validation failed" in str(exc_info.value)


def test_error_response_fallback_to_text() -> None:
    """send() raises NemoHTTPError with raw text when no JSON detail."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        500,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/x"),
        text="Internal Server Error",
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)

    with pytest.raises(NemoHTTPError) as exc_info:
        client.send(GET_ITEM(name="x"))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal Server Error"


def test_error_response_raises_specific_subclass() -> None:
    """send() raises status-code-specific NemoHTTPError subclass."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        404,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/missing"),
        json={"detail": "Not found"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)

    with pytest.raises(NotFoundError) as exc_info:
        client.send(GET_ITEM(name="missing"))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not found"


def test_success_response_validation_error_uses_client_error_contract() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    response = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": "not-an-integer", "name": "alice"},
    )
    mock_http.request.return_value = response

    with pytest.raises(NemoResponseValidationError) as exc_info:
        NemoClient(base_url=BASE, http_client=mock_http).send(GET_ITEM(name="alice"))

    assert exc_info.value.http_response is response
    assert exc_info.value.status_code == 200
    assert exc_info.value.body == {"id": "not-an-integer", "name": "alice"}


# ---------------------------------------------------------------------------
# Per-request headers
# ---------------------------------------------------------------------------


def test_extra_headers_merged_into_request() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(GET_ITEM(name="alice"), headers={"Accept": "application/octet-stream"})

    _, kwargs = mock_http.request.call_args
    assert kwargs["headers"]["Accept"] == "application/octet-stream"


def test_extra_headers_dont_override_content_type() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(CREATE_ITEM(ItemRequest(name="alice")), headers={"X-Custom": "value"})

    _, kwargs = mock_http.request.call_args
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["headers"]["X-Custom"] == "value"


# ---------------------------------------------------------------------------
# Response carries request
# ---------------------------------------------------------------------------


def test_response_carries_prepared_request() -> None:
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
        json={"id": 1, "name": "alice"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    resp = client.send(GET_ITEM(name="alice"))

    assert resp.request is not None
    assert resp.request.method == "GET"
    assert resp.request.path_params == {"name": "alice"}


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_send_raises_on_non_2xx() -> None:
    """send() must raise immediately on non-2xx."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        403,
        request=httpx.Request("PUT", f"{BASE}/apis/test/upload"),
        json={"detail": "Access denied"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)

    with pytest.raises(NemoHTTPError) as exc_info:
        client.send(CREATE_ITEM(ItemRequest(name="x")))

    assert exc_info.value.status_code == 403


def test_query_param_dicts_are_json_serialized() -> None:
    """Dict query params must be JSON-serialized, not Python repr."""
    from abc import abstractmethod

    from nemo_platform_plugin.client.endpoint import get

    @get("/apis/test/v2/items")
    @abstractmethod
    def list_items(*, query_params: dict | None = None) -> ItemResponse: ...

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/items"),
        json={"id": 1, "name": "x"},
    )

    client = NemoClient(base_url=BASE, http_client=mock_http)
    client.send(list_items(query_params={"filter": {"name": "test"}}))

    _, kwargs = mock_http.request.call_args
    filter_value = kwargs["params"]["filter"]
    assert filter_value == '{"name": "test"}', f"Expected JSON string, got: {filter_value}"
