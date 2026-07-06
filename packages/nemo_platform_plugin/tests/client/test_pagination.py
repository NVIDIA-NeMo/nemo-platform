# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Paginated[T] — automatic pagination via return type marker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.endpoint import get
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.client.response import AsyncNemoPaginatedResponse, NemoPaginatedResponse
from nemo_platform_plugin.client.types import OffsetPagination, Paginated, RetryPolicy
from pydantic import BaseModel

BASE = "http://test:8000"


class Item(BaseModel):
    id: int
    name: str


@get("/apis/test/v2/workspaces/{workspace}/items")
def LIST_ITEMS(*, workspace: str | None = None) -> Paginated[Item]:
    raise NotImplementedError


def _page_response(items: list[dict], page: int, total_pages: int, page_size: int = 2) -> httpx.Response:
    """Helper to build a paginated response matching NemoListResponse format."""
    return httpx.Response(
        200,
        request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
        json={
            "data": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "current_page_size": len(items),
                "total_pages": total_pages,
                "total_results": total_pages * page_size,
            },
        },
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class TestPaginatedSync:
    def test_single_page_iteration(self) -> None:
        """When total_pages=1, iterating should yield items from only one page."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _page_response(
            [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}], page=1, total_pages=1
        )

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        assert isinstance(resp, NemoPaginatedResponse)
        items = list(resp.items())
        assert len(items) == 2
        assert items[0].name == "a"
        assert items[1].name == "b"
        # Only one request made (no additional page fetches)
        assert mock_http.request.call_count == 1

    def test_multi_page_iteration(self) -> None:
        """Iterating should automatically fetch all pages."""
        mock_http = MagicMock(spec=httpx.Client)
        # First call (page 1) via send()
        mock_http.request.side_effect = [
            _page_response([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}], page=1, total_pages=3),
            # Pages 2 and 3 fetched by _fetch_page
            _page_response([{"id": 3, "name": "c"}, {"id": 4, "name": "d"}], page=2, total_pages=3),
            _page_response([{"id": 5, "name": "e"}], page=3, total_pages=3),
        ]

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        items = list(resp.items())
        assert len(items) == 5
        assert [i.name for i in items] == ["a", "b", "c", "d", "e"]
        assert mock_http.request.call_count == 3

    def test_data_returns_page_result_with_metadata(self) -> None:
        """data() returns a PageResult with items and pagination metadata."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _page_response([{"id": 1, "name": "a"}], page=1, total_pages=5)

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        page = resp.page()
        assert len(page.items) == 1
        assert page.items[0].name == "a"
        assert page.page == 1
        assert page.total_pages == 5
        assert page.total_results == 10
        assert page.page_size == 2
        # No additional requests for data()
        assert mock_http.request.call_count == 1

    def test_empty_page(self) -> None:
        """Empty data list should yield nothing."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _page_response([], page=1, total_pages=1)

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        items = list(resp.items())
        assert items == []

    def test_no_pagination_metadata(self) -> None:
        """When pagination is None, treat as single page."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            200,
            request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
            json={"data": [{"id": 1, "name": "a"}]},
        )

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        items = list(resp.items())
        assert len(items) == 1
        assert mock_http.request.call_count == 1

    def test_page_query_param_passed_on_subsequent_pages(self) -> None:
        """Subsequent page fetches should include page=N in query params."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            _page_response([{"id": 1, "name": "a"}], page=1, total_pages=2),
            _page_response([{"id": 2, "name": "b"}], page=2, total_pages=2),
        ]

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())
        list(resp.items())  # consume all pages

        # Second call should have page=2 in params
        second_call_params = mock_http.request.call_args_list[1][1]["params"]
        assert second_call_params["page"] == 2


# ---------------------------------------------------------------------------
# Via method() descriptor
# ---------------------------------------------------------------------------


class TestPaginatedViaMethod:
    def test_method_descriptor_returns_paginated_response(self) -> None:
        """method() wrapping a Paginated endpoint should return NemoPaginatedResponse."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _page_response([{"id": 1, "name": "a"}], page=1, total_pages=1)

        class _Methods:
            list_items = method(LIST_ITEMS)

        class TestClient(_Methods, NemoClient):
            pass

        client = TestClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.list_items()

        # Client options are applied but shouldn't break pagination
        items = list(resp.items())
        assert len(items) == 1
        assert items[0].name == "a"


# ---------------------------------------------------------------------------
# Async
# ---------------------------------------------------------------------------


class TestPaginatedAsync:
    @pytest.mark.asyncio
    async def test_async_multi_page_iteration(self) -> None:
        """Async iteration should automatically fetch all pages."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.side_effect = [
            _page_response([{"id": 1, "name": "a"}], page=1, total_pages=2),
            _page_response([{"id": 2, "name": "b"}], page=2, total_pages=2),
        ]

        client = AsyncNemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = await client.send(LIST_ITEMS())

        assert isinstance(resp, AsyncNemoPaginatedResponse)
        items = [item async for item in resp.items()]
        assert len(items) == 2
        assert items[0].name == "a"
        assert items[1].name == "b"

    @pytest.mark.asyncio
    async def test_async_data_returns_page_result(self) -> None:
        """Async data() returns a PageResult with metadata."""
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _page_response([{"id": 1, "name": "a"}], page=1, total_pages=3)

        client = AsyncNemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = await client.send(LIST_ITEMS())

        page = resp.page()
        assert len(page.items) == 1
        assert page.page == 1
        assert page.total_pages == 3
        assert mock_http.request.call_count == 1


# ---------------------------------------------------------------------------
# Retry on subsequent pages
# ---------------------------------------------------------------------------


class TestPaginatedRetry:
    def test_retry_on_subsequent_page_503(self) -> None:
        """A 503 on page 2 should be retried when a retry policy is configured."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            # Page 1: success
            _page_response([{"id": 1, "name": "a"}], page=1, total_pages=2),
            # Page 2: first attempt 503, second attempt success
            httpx.Response(
                503,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
                json={"detail": "unavailable"},
            ),
            _page_response([{"id": 2, "name": "b"}], page=2, total_pages=2),
        ]

        client = NemoClient(
            base_url=BASE,
            workspace="default",
            http_client=mock_http,
            retry=RetryPolicy(max_retries=2, backoff_base=0.0),
        )
        items = list(client.send(LIST_ITEMS()).items())

        assert len(items) == 2
        assert [i.name for i in items] == ["a", "b"]
        assert mock_http.request.call_count == 3  # page 1 + page 2 fail + page 2 retry


# ---------------------------------------------------------------------------
# Custom pagination strategy
# ---------------------------------------------------------------------------


class ResultsPagination(OffsetPagination):
    """Custom strategy: items in 'results', page param is 'offset'."""

    items_field = "results"
    page_param = "offset"


@get("/apis/test/v2/workspaces/{workspace}/things")
def LIST_THINGS(*, workspace: str | None = None) -> Paginated[Item, ResultsPagination]:
    raise NotImplementedError


class TestCustomStrategy:
    def test_custom_items_field(self) -> None:
        """Custom strategy should extract items from the configured field."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = httpx.Response(
            200,
            request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/things"),
            json={
                "results": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
                "pagination": {
                    "page": 1,
                    "page_size": 10,
                    "current_page_size": 2,
                    "total_pages": 1,
                    "total_results": 2,
                },
            },
        )

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_THINGS())

        items = list(resp.items())
        assert len(items) == 2
        assert items[0].name == "a"

    def test_custom_page_param(self) -> None:
        """Custom strategy should use the configured page query param."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            httpx.Response(
                200,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/things"),
                json={
                    "results": [{"id": 1, "name": "a"}],
                    "pagination": {
                        "page": 1,
                        "page_size": 1,
                        "current_page_size": 1,
                        "total_pages": 2,
                        "total_results": 2,
                    },
                },
            ),
            httpx.Response(
                200,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/things"),
                json={
                    "results": [{"id": 2, "name": "b"}],
                    "pagination": {
                        "page": 2,
                        "page_size": 1,
                        "current_page_size": 1,
                        "total_pages": 2,
                        "total_results": 2,
                    },
                },
            ),
        ]

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        items = list(client.send(LIST_THINGS()).items())

        assert len(items) == 2
        # Verify the second call used "offset" not "page"
        second_call_params = mock_http.request.call_args_list[1][1]["params"]
        assert "offset" in second_call_params
        assert second_call_params["offset"] == 2


# ---------------------------------------------------------------------------
# Infra hardening: empty-page guard, server-echoed page advancement, caching
# ---------------------------------------------------------------------------


class TestPaginationHardening:
    def test_stops_on_empty_page_before_total_pages(self) -> None:
        """If a page returns no items before total_pages is reached, stop.

        Guards against a server reporting more pages than it can serve (stale
        count, deletions mid-scan) — without this the client would loop fetching
        empty pages up to total_pages.
        """
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            _page_response([{"id": 1, "name": "a"}], page=1, total_pages=5),
            # Page 2 comes back empty even though total_pages says 5
            _page_response([], page=2, total_pages=5),
        ]

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        items = list(client.send(LIST_ITEMS()).items())

        assert [i.name for i in items] == ["a"]
        # page 1 + page 2 (empty) — no page 3/4/5 fetched
        assert mock_http.request.call_count == 2

    def test_advances_from_server_echoed_page(self) -> None:
        """Next-page number is derived from the body's echoed page, not a counter.

        Even if the server renumbers pages, advancement tracks what the server
        actually returned.
        """
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            # Server echoes page=5 for the first response
            _page_response([{"id": 1, "name": "a"}], page=5, total_pages=6),
            _page_response([{"id": 2, "name": "b"}], page=6, total_pages=6),
        ]

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        items = list(client.send(LIST_ITEMS()).items())

        assert [i.name for i in items] == ["a", "b"]
        # Second fetch requests page 6 (echoed 5 + 1), not page 2
        second_call_params = mock_http.request.call_args_list[1][1]["params"]
        assert second_call_params["page"] == 6

    def test_page_is_cached(self) -> None:
        """Repeated .page() calls parse the first response only once."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _page_response([{"id": 1, "name": "a"}], page=1, total_pages=1)

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        first = resp.page()
        second = resp.page()
        assert first is second
        assert mock_http.request.call_count == 1

    @pytest.mark.asyncio
    async def test_async_stops_on_empty_page(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.side_effect = [
            _page_response([{"id": 1, "name": "a"}], page=1, total_pages=4),
            _page_response([], page=2, total_pages=4),
        ]

        client = AsyncNemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        items = [item async for item in (await client.send(LIST_ITEMS())).items()]

        assert [i.name for i in items] == ["a"]
        assert mock_http.request.call_count == 2

    @pytest.mark.asyncio
    async def test_async_page_is_cached(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.request.return_value = _page_response([{"id": 1, "name": "a"}], page=1, total_pages=1)

        client = AsyncNemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = await client.send(LIST_ITEMS())

        assert resp.page() is resp.page()
        assert mock_http.request.call_count == 1


class TestDefaultRetry:
    def test_retries_on_by_default(self) -> None:
        """A client constructed without an explicit retry policy still retries 503s."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.side_effect = [
            httpx.Response(
                503,
                request=httpx.Request("GET", f"{BASE}/apis/test/v2/workspaces/default/items"),
                json={"detail": "unavailable"},
            ),
            _page_response([{"id": 1, "name": "a"}], page=1, total_pages=1),
        ]

        # No retry= passed → DEFAULT_RETRY_POLICY (backoff patched to 0 for speed).
        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        client._retry = RetryPolicy(backoff_base=0.0)  # keep default codes, zero sleep
        items = list(client.send(LIST_ITEMS()).items())

        assert [i.name for i in items] == ["a"]
        assert mock_http.request.call_count == 2  # first 503 + retry success
