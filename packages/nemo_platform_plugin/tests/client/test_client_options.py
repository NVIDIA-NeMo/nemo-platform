# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for client-side options (exist_ok), RetryPolicy, and param validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.client.types import PreparedRequest, RetryPolicy
from pydantic import BaseModel

BASE = "http://test:8000"


class ItemRequest(BaseModel):
    name: str


class ItemResponse(BaseModel):
    id: int
    name: str


# ---------------------------------------------------------------------------
# Endpoint definitions with client options
# ---------------------------------------------------------------------------


@post("/apis/test/v2/items")
def CREATE_ITEM(body: ItemRequest, *, exist_ok: bool = False) -> ItemResponse:
    raise NotImplementedError


@get("/apis/test/v2/items/{name}")
def GET_ITEM(*, name: str) -> ItemResponse:
    raise NotImplementedError


@delete("/apis/test/v2/items/{name}")
def DELETE_ITEM(*, name: str) -> None:
    raise NotImplementedError


# ---------------------------------------------------------------------------
# exist_ok: stripped from request, stashed in client_options
# ---------------------------------------------------------------------------


class TestExistOkOption:
    def test_exist_ok_stripped_from_request(self) -> None:
        prepared = CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True)

        assert isinstance(prepared, PreparedRequest)
        assert prepared.content is not None
        assert prepared.client_options is not None
        assert prepared.client_options["exist_ok"] is True

    def test_exist_ok_default_false(self) -> None:
        prepared = CREATE_ITEM(ItemRequest(name="alice"))

        assert prepared.client_options is not None
        assert prepared.client_options["exist_ok"] is False

    def test_endpoint_without_options_has_none(self) -> None:
        prepared = GET_ITEM(name="alice")
        assert prepared.client_options is None


# ---------------------------------------------------------------------------
# exist_ok: applied via send()
# ---------------------------------------------------------------------------


class TestExistOkViaSend:
    def test_exist_ok_via_send_swallows_409(self) -> None:
        """exist_ok should work when calling client.send() directly."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            409,
            request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
            json={"id": 1, "name": "alice"},
        )

        client = NemoClient(base_url=BASE, http_client=mock_http)
        resp = client.send(CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True))

        assert resp.http_response.status_code == 409
        assert resp.body is not None
        assert resp.body.name == "alice"


# ---------------------------------------------------------------------------
# exist_ok: applied via EndpointMethod
# ---------------------------------------------------------------------------


class TestExistOkViaMethod:
    def test_exist_ok_true_swallows_409(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            409,
            request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
            json={"id": 1, "name": "alice"},
        )

        class _Methods:
            create_item = method(CREATE_ITEM)

        class TestClient(_Methods, NemoClient):
            pass

        client = TestClient(base_url=BASE, http_client=mock_http)
        resp = client.create_item(body=ItemRequest(name="alice"), exist_ok=True)

        assert resp.http_response.status_code == 409
        assert resp.body is not None
        assert resp.body.name == "alice"

    def test_exist_ok_false_returns_409_as_is(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            409,
            request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
            json={"detail": "Already exists"},
        )

        class _Methods:
            create_item = method(CREATE_ITEM)

        class TestClient(_Methods, NemoClient):
            pass

        client = TestClient(base_url=BASE, http_client=mock_http)
        resp = client.create_item(body=ItemRequest(name="alice"))

        assert resp.http_response.status_code == 409
        assert resp.body is None

    def test_exist_ok_true_non_409_passes_through(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            201,
            request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
            json={"id": 1, "name": "alice"},
        )

        class _Methods:
            create_item = method(CREATE_ITEM)

        class TestClient(_Methods, NemoClient):
            pass

        client = TestClient(base_url=BASE, http_client=mock_http)
        resp = client.create_item(body=ItemRequest(name="alice"), exist_ok=True)

        assert resp.http_response.status_code == 201
        assert resp.body.name == "alice"


# ---------------------------------------------------------------------------
# Param validation at decoration time
# ---------------------------------------------------------------------------


class TestParamValidation:
    def test_unknown_param_raises_at_decoration_time(self) -> None:
        with pytest.raises(TypeError, match="unrecognised parameters"):

            @post("/apis/test/v2/items")
            def bad_endpoint(body: ItemRequest, *, bogus: str = "oops") -> ItemResponse:
                raise NotImplementedError

    def test_blessed_param_is_allowed(self) -> None:
        @post("/apis/test/v2/items")
        def ok_endpoint(body: ItemRequest, *, exist_ok: bool = False) -> ItemResponse:
            raise NotImplementedError

        prepared = ok_endpoint(ItemRequest(name="x"))
        assert isinstance(prepared, PreparedRequest)

    def test_path_params_are_allowed(self) -> None:
        @get("/items/{workspace}/{name}")
        def ok_endpoint(*, workspace: str, name: str) -> ItemResponse:
            raise NotImplementedError

        prepared = ok_endpoint(workspace="default", name="x")
        assert prepared.path_params == {"workspace": "default", "name": "x"}


# ---------------------------------------------------------------------------
# RetryPolicy: client-level default
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_retry_on_503(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            httpx.Response(
                503,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
                json={"detail": "Service Unavailable"},
            ),
            httpx.Response(
                200,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
                json={"id": 1, "name": "alice"},
            ),
        ]

        client = NemoClient(
            base_url=BASE,
            http_client=mock_http,
            retry=RetryPolicy(max_retries=2, backoff_base=0.0),
        )
        resp = client.send(GET_ITEM(name="alice"))

        assert resp.http_response.status_code == 200
        assert resp.body.name == "alice"
        assert mock_http.request.call_count == 2

    def test_retry_exhausted_returns_last_response(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            503,
            request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
            json={"detail": "Service Unavailable"},
        )

        client = NemoClient(
            base_url=BASE,
            http_client=mock_http,
            retry=RetryPolicy(max_retries=2, backoff_base=0.0),
        )
        resp = client.send(GET_ITEM(name="alice"))

        assert resp.http_response.status_code == 503
        assert mock_http.request.call_count == 3

    def test_no_retry_on_non_retryable_status(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            404,
            request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
            json={"detail": "Not found"},
        )

        client = NemoClient(
            base_url=BASE,
            http_client=mock_http,
            retry=RetryPolicy(max_retries=2, backoff_base=0.0),
        )
        resp = client.send(GET_ITEM(name="alice"))

        assert resp.http_response.status_code == 404
        assert mock_http.request.call_count == 1

    def test_retry_on_transport_error(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.Response(
                200,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
                json={"id": 1, "name": "alice"},
            ),
        ]

        client = NemoClient(
            base_url=BASE,
            http_client=mock_http,
            retry=RetryPolicy(max_retries=2, backoff_base=0.0),
        )
        resp = client.send(GET_ITEM(name="alice"))

        assert resp.body.name == "alice"
        assert mock_http.request.call_count == 2

    def test_per_request_retry_overrides_client_default(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            503,
            request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
            json={"detail": "unavailable"},
        )

        client = NemoClient(
            base_url=BASE,
            http_client=mock_http,
            retry=RetryPolicy(max_retries=5, backoff_base=0.0),
        )
        client.send(GET_ITEM(name="alice"), retry=RetryPolicy(max_retries=1, backoff_base=0.0))

        assert mock_http.request.call_count == 2

    def test_no_retry_without_policy(self) -> None:
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            503,
            request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
            json={"detail": "unavailable"},
        )

        client = NemoClient(base_url=BASE, http_client=mock_http)
        resp = client.send(GET_ITEM(name="alice"))

        assert resp.http_response.status_code == 503
        assert mock_http.request.call_count == 1


# ---------------------------------------------------------------------------
# Async: exist_ok
# ---------------------------------------------------------------------------


class TestAsyncExistOk:
    @pytest.mark.asyncio
    async def test_exist_ok_true_swallows_409_async(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = httpx.Response(
            409,
            request=httpx.Request("POST", f"{BASE}/apis/test/v2/items"),
            json={"id": 1, "name": "alice"},
        )

        class _Methods:
            create_item = method(CREATE_ITEM)

        class TestAsyncClient(_Methods, AsyncNemoClient):
            pass

        client = TestAsyncClient(base_url=BASE, http_client=mock_http)
        resp = await client.create_item(body=ItemRequest(name="alice"), exist_ok=True)

        assert resp.http_response.status_code == 409
        assert resp.body is not None
        assert resp.body.name == "alice"


# ---------------------------------------------------------------------------
# Async: RetryPolicy
# ---------------------------------------------------------------------------


class TestAsyncRetryPolicy:
    @pytest.mark.asyncio
    async def test_retry_on_503_async(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.side_effect = [
            httpx.Response(
                503,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
                json={"detail": "unavailable"},
            ),
            httpx.Response(
                200,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/items/alice"),
                json={"id": 1, "name": "alice"},
            ),
        ]

        client = AsyncNemoClient(
            base_url=BASE,
            http_client=mock_http,
            retry=RetryPolicy(max_retries=2, backoff_base=0.0),
        )
        resp = await client.send(GET_ITEM(name="alice"))

        assert resp.http_response.status_code == 200
        assert resp.body.name == "alice"
        assert mock_http.request.call_count == 2
