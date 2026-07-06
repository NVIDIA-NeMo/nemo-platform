# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for client-side options (exist_ok), RetryPolicy, and param validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.errors import ConflictError, NemoHTTPError, NotFoundError
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


@get("/apis/test/v2/items/{name}")
def GET_ITEM(*, name: str) -> ItemResponse:
    raise NotImplementedError


@delete("/apis/test/v2/items/{name}")
def DELETE_ITEM(*, name: str) -> None:
    raise NotImplementedError


def _get_item_on_conflict(body: ItemRequest, workspace: str | None) -> PreparedRequest[ItemResponse]:
    """Resolver: on a create 409, retrieve the existing item by name."""
    return GET_ITEM(name=body.name)


@post("/apis/test/v2/items", get_on_conflict=_get_item_on_conflict)
def CREATE_ITEM(body: ItemRequest, *, exist_ok: bool = False) -> ItemResponse:
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
# get_on_conflict: resolver wiring at request-build time
# ---------------------------------------------------------------------------


class TestConflictResolverWiring:
    def test_resolver_builds_get_at_request_time(self) -> None:
        """The create request carries a prebuilt GET derived from the body."""
        prepared = CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True)

        assert prepared.on_conflict_get is not None
        get_req = prepared.on_conflict_get
        assert get_req.method == "GET"
        assert get_req.path_template == "/apis/test/v2/items/{name}"
        assert get_req.path_params == {"name": "alice"}

    def test_endpoint_without_resolver_has_no_on_conflict_get(self) -> None:
        # A create endpoint that declares no resolver (and no exist_ok) carries
        # no prebuilt GET.
        @post("/apis/test/v2/items")
        def create_plain(body: ItemRequest) -> ItemResponse:
            raise NotImplementedError

        prepared = create_plain(ItemRequest(name="alice"))
        assert prepared.on_conflict_get is None


# ---------------------------------------------------------------------------
# exist_ok: resolved via send() by replaying the linked GET on 409
# ---------------------------------------------------------------------------


def _mock_http(*responses: httpx.Response) -> MagicMock:
    """A sync httpx.Client whose .request() returns the given responses in order."""
    mock = MagicMock(spec=httpx.Client)
    mock.request.side_effect = list(responses)
    return mock


def _resp(
    status: int, body: dict, http_method: str = "POST", url: str = f"{BASE}/apis/test/v2/items"
) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request(http_method, url), json=body)


class TestExistOkViaSend:
    def test_409_with_exist_ok_replays_get_and_returns_entity(self) -> None:
        """409 (real error body) + exist_ok -> auto-GET returns the existing entity."""
        mock = _mock_http(
            _resp(409, {"detail": "Item 'alice' already exists"}),
            _resp(200, {"id": 7, "name": "alice"}, http_method="GET", url=f"{BASE}/apis/test/v2/items/alice"),
        )
        client = NemoClient(base_url=BASE, http_client=mock)

        resp = client.send(CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True))

        assert resp.body is not None
        assert resp.body.id == 7
        assert resp.body.name == "alice"
        # POST then follow-up GET.
        assert mock.request.call_count == 2
        assert mock.request.call_args_list[1].args[0] == "GET"

    def test_409_without_exist_ok_raises_conflict(self) -> None:
        mock = _mock_http(_resp(409, {"detail": "Item 'alice' already exists"}))
        client = NemoClient(base_url=BASE, http_client=mock)

        with pytest.raises(ConflictError) as exc_info:
            client.send(CREATE_ITEM(ItemRequest(name="alice")))

        assert exc_info.value.status_code == 409
        assert mock.request.call_count == 1  # no follow-up GET

    def test_non_409_with_exist_ok_passes_through(self) -> None:
        mock = _mock_http(_resp(201, {"id": 1, "name": "alice"}))
        client = NemoClient(base_url=BASE, http_client=mock)

        resp = client.send(CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True))

        assert resp.http_response.status_code == 201
        assert resp.body is not None
        assert resp.body.name == "alice"
        assert mock.request.call_count == 1

    def test_get_404_after_409_is_surfaced(self) -> None:
        """Entity deleted between the 409 and the follow-up GET -> NotFoundError."""
        mock = _mock_http(
            _resp(409, {"detail": "Item 'alice' already exists"}),
            _resp(404, {"detail": "not found"}, http_method="GET", url=f"{BASE}/apis/test/v2/items/alice"),
        )
        client = NemoClient(base_url=BASE, http_client=mock)

        with pytest.raises(NotFoundError):
            client.send(CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True))

    def test_caller_headers_are_preserved_on_conflict_replay(self) -> None:
        """Per-request headers passed to send() are carried onto the follow-up GET."""
        mock = _mock_http(
            _resp(409, {"detail": "Item 'alice' already exists"}),
            _resp(200, {"id": 7, "name": "alice"}, http_method="GET", url=f"{BASE}/apis/test/v2/items/alice"),
        )
        client = NemoClient(base_url=BASE, http_client=mock)

        client.send(CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True), headers={"X-Trace": "abc"})

        get_headers = mock.request.call_args_list[1].kwargs["headers"]
        assert get_headers["X-Trace"] == "abc"


class TestExistOkViaMethod:
    def test_flat_method_call_resolves_conflict(self) -> None:
        """client.create_item(..., exist_ok=True) returns the entity on 409."""
        mock = _mock_http(
            _resp(409, {"detail": "Item 'alice' already exists"}),
            _resp(200, {"id": 7, "name": "alice"}, http_method="GET", url=f"{BASE}/apis/test/v2/items/alice"),
        )

        class _Methods:
            create_item = method(CREATE_ITEM)

        class TestClient(_Methods, NemoClient):
            pass

        client = TestClient(base_url=BASE, http_client=mock)
        resp = client.create_item(body=ItemRequest(name="alice"), exist_ok=True)

        assert resp.body is not None
        assert resp.body.id == 7


class TestAsyncExistOkViaSend:
    @pytest.mark.asyncio
    async def test_409_with_exist_ok_replays_get_and_returns_entity(self) -> None:
        mock = AsyncMock(spec=httpx.AsyncClient)
        mock.request.side_effect = [
            _resp(409, {"detail": "Item 'alice' already exists"}),
            _resp(200, {"id": 7, "name": "alice"}, http_method="GET", url=f"{BASE}/apis/test/v2/items/alice"),
        ]
        client = AsyncNemoClient(base_url=BASE, http_client=mock)

        resp = await client.send(CREATE_ITEM(ItemRequest(name="alice"), exist_ok=True))

        assert resp.body is not None
        assert resp.body.id == 7
        assert resp.body.name == "alice"
        assert mock.request.call_count == 2

    @pytest.mark.asyncio
    async def test_409_without_exist_ok_raises_conflict(self) -> None:
        mock = AsyncMock(spec=httpx.AsyncClient)
        mock.request.side_effect = [_resp(409, {"detail": "Item 'alice' already exists"})]
        client = AsyncNemoClient(base_url=BASE, http_client=mock)

        with pytest.raises(ConflictError):
            await client.send(CREATE_ITEM(ItemRequest(name="alice")))
        assert mock.request.call_count == 1


class TestAsyncExistOkViaMethod:
    @pytest.mark.asyncio
    async def test_flat_method_call_resolves_conflict(self) -> None:
        """await client.create_item(..., exist_ok=True) returns the entity on 409."""
        mock = AsyncMock(spec=httpx.AsyncClient)
        mock.request.side_effect = [
            _resp(409, {"detail": "Item 'alice' already exists"}),
            _resp(200, {"id": 7, "name": "alice"}, http_method="GET", url=f"{BASE}/apis/test/v2/items/alice"),
        ]

        class _Methods:
            create_item = method(CREATE_ITEM)

        class TestAsyncClient(_Methods, AsyncNemoClient):
            pass

        client = TestAsyncClient(base_url=BASE, http_client=mock)
        resp = await client.create_item(body=ItemRequest(name="alice"), exist_ok=True)

        assert resp.body is not None
        assert resp.body.id == 7
        assert mock.request.call_count == 2


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
        @post("/apis/test/v2/items", get_on_conflict=_get_item_on_conflict)
        def ok_endpoint(body: ItemRequest, *, exist_ok: bool = False) -> ItemResponse:
            raise NotImplementedError

        prepared = ok_endpoint(ItemRequest(name="x"))
        assert isinstance(prepared, PreparedRequest)

    def test_exist_ok_without_resolver_raises_at_decoration_time(self) -> None:
        # exist_ok is inert without a resolver to fetch the entity on 409, so it
        # is rejected up front rather than failing on the first real conflict.
        with pytest.raises(TypeError, match="get_on_conflict"):

            @post("/apis/test/v2/items")
            def bad_endpoint(body: ItemRequest, *, exist_ok: bool = False) -> ItemResponse:
                raise NotImplementedError

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

    def test_retry_exhausted_raises(self) -> None:
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

        with pytest.raises(NemoHTTPError) as exc_info:
            client.send(GET_ITEM(name="alice"))

        assert exc_info.value.status_code == 503
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

        with pytest.raises(NemoHTTPError) as exc_info:
            client.send(GET_ITEM(name="alice"))

        assert exc_info.value.status_code == 404
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

        with pytest.raises(NemoHTTPError):
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

        with pytest.raises(NemoHTTPError) as exc_info:
            client.send(GET_ITEM(name="alice"))

        assert exc_info.value.status_code == 503
        assert mock_http.request.call_count == 1


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
