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
        items = list(resp)
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

        items = list(resp)
        assert len(items) == 5
        assert [i.name for i in items] == ["a", "b", "c", "d", "e"]
        assert mock_http.request.call_count == 3

    def test_data_returns_page_result_with_metadata(self) -> None:
        """data() returns a PageResult with items and pagination metadata."""
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.request.return_value = _page_response([{"id": 1, "name": "a"}], page=1, total_pages=5)

        client = NemoClient(base_url=BASE, workspace="default", http_client=mock_http)
        resp = client.send(LIST_ITEMS())

        page = resp.data()
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

        items = list(resp)
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

        items = list(resp)
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
        list(resp)  # consume all pages

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
        items = list(resp)
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
        items = [item async for item in resp]
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

        page = resp.data()
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
        items = list(client.send(LIST_ITEMS()))

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

        items = list(resp)
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
        items = list(client.send(LIST_THINGS()))

        assert len(items) == 2
        # Verify the second call used "offset" not "page"
        second_call_params = mock_http.request.call_args_list[1][1]["params"]
        assert "offset" in second_call_params
        assert second_call_params["offset"] == 2
