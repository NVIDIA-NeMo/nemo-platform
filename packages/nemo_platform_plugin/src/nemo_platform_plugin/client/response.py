# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP response wrappers for JSON, binary, and streaming endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Generic, TypeVar

import httpx
from nemo_platform_plugin.client.types import OffsetPagination, PaginationStrategy, PreparedRequest
from pydantic import BaseModel

ResponseT = TypeVar("ResponseT")
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class NemoResponse(Generic[ResponseT]):
    """Typed HTTP response for JSON endpoints.

    Example::

        resp = client.send(endpoints.get_user(workspace="default"))
        resp.body             # UserResponse
        resp.http_response    # full httpx.Response

        user = resp.data()    # raises on non-2xx, otherwise returns body
    """

    http_response: httpx.Response
    body: ResponseT
    request: PreparedRequest

    def data(self) -> ResponseT:
        """Return the body if the status is 2xx, otherwise raise."""
        if not (200 <= self.http_response.status_code < 300):
            raise NemoHTTPError(self.http_response)
        return self.body


# ---------------------------------------------------------------------------
# Sync streaming responses
# ---------------------------------------------------------------------------


class NemoBinaryResponse:
    """Sync response for binary download endpoints.

    Use as a context manager::

        with client.send(endpoints.download(...)) as resp:
            data = resp.read()       # all bytes at once
            # or: for chunk in resp  # iterate chunks
    """

    def __init__(self, stream_ctx: AbstractContextManager[httpx.Response], request: PreparedRequest) -> None:
        self._stream_ctx = stream_ctx
        self._response: httpx.Response | None = None
        self.request = request

    @property
    def http_response(self) -> httpx.Response:
        assert self._response is not None, "Must enter context manager before accessing response"
        return self._response

    def read(self) -> bytes:
        """Read and return the entire response body as bytes."""
        return self.http_response.read()

    def __iter__(self) -> Iterator[bytes]:
        return self.http_response.iter_bytes()

    def __enter__(self) -> NemoBinaryResponse:
        self._response = self._stream_ctx.__enter__()
        self._response.raise_for_status()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        self._stream_ctx.__exit__(exc_type, exc_val, exc_tb)


class NemoStreamResponse(Generic[ModelT]):
    """Sync response for SSE/NDJSON streaming endpoints.

    Use as a context manager::

        with client.send(ChatEndpoint(...)) as resp:
            for chunk in resp:
                print(chunk.text)
    """

    def __init__(
        self,
        stream_ctx: AbstractContextManager[httpx.Response],
        model_type: type[ModelT],
        request: PreparedRequest,
    ) -> None:
        self._stream_ctx = stream_ctx
        self._model_type = model_type
        self._response: httpx.Response | None = None
        self.request = request

    @property
    def http_response(self) -> httpx.Response:
        assert self._response is not None, "Must enter context manager before accessing response"
        return self._response

    def __iter__(self) -> Iterator[ModelT]:
        for line in self.http_response.iter_lines():
            line = line.strip()
            if line:
                yield self._model_type.model_validate_json(line)

    def __enter__(self) -> NemoStreamResponse[ModelT]:
        self._response = self._stream_ctx.__enter__()
        self._response.raise_for_status()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        self._stream_ctx.__exit__(exc_type, exc_val, exc_tb)


# ---------------------------------------------------------------------------
# Async streaming responses
# ---------------------------------------------------------------------------


class AsyncNemoBinaryResponse:
    """Async response for binary download endpoints.

    Use as an async context manager::

        async with client.send(endpoints.download(...)) as resp:
            data = await resp.read()           # all bytes at once
            # or: async for chunk in resp      # iterate chunks
    """

    def __init__(self, stream_ctx: AbstractAsyncContextManager[httpx.Response], request: PreparedRequest) -> None:
        self._stream_ctx = stream_ctx
        self._response: httpx.Response | None = None
        self.request = request

    @property
    def http_response(self) -> httpx.Response:
        assert self._response is not None, "Must enter async context manager before accessing response"
        return self._response

    async def read(self) -> bytes:
        """Read and return the entire response body as bytes."""
        return await self.http_response.aread()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.http_response.aiter_bytes():
            yield chunk

    async def __aenter__(self) -> AsyncNemoBinaryResponse:
        self._response = await self._stream_ctx.__aenter__()
        self._response.raise_for_status()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        await self._stream_ctx.__aexit__(exc_type, exc_val, exc_tb)


class AsyncNemoStreamResponse(Generic[ModelT]):
    """Async response for SSE/NDJSON streaming endpoints.

    Use as an async context manager::

        async with client.send(ChatEndpoint(...)) as resp:
            async for chunk in resp:
                print(chunk.text)
    """

    def __init__(
        self,
        stream_ctx: AbstractAsyncContextManager[httpx.Response],
        model_type: type[ModelT],
        request: PreparedRequest,
    ) -> None:
        self._stream_ctx = stream_ctx
        self._model_type = model_type
        self._response: httpx.Response | None = None
        self.request = request

    @property
    def http_response(self) -> httpx.Response:
        assert self._response is not None, "Must enter async context manager before accessing response"
        return self._response

    async def __aiter__(self) -> AsyncIterator[ModelT]:
        async for line in self.http_response.aiter_lines():
            line = line.strip()
            if line:
                yield self._model_type.model_validate_json(line)

    async def __aenter__(self) -> AsyncNemoStreamResponse[ModelT]:
        self._response = await self._stream_ctx.__aenter__()
        self._response.raise_for_status()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        await self._stream_ctx.__aexit__(exc_type, exc_val, exc_tb)


# ---------------------------------------------------------------------------
# Paginated responses
# ---------------------------------------------------------------------------


# Type aliases for the page-fetching callbacks used by paginated responses.
# The page value is int for offset-based or str for cursor-based pagination.
SyncPageFetcher = Callable[[PreparedRequest, Any], httpx.Response]
AsyncPageFetcher = Callable[[PreparedRequest, Any], Coroutine[Any, Any, httpx.Response]]


@dataclass(frozen=True, slots=True)
class PageResult(Generic[ModelT]):
    """A single page of results with pagination metadata.

    Returned by :meth:`NemoPaginatedResponse.data` for callers who want
    one page at a time rather than auto-iterating all pages::

        resp = client.send(list_items())
        page = resp.data()
        print(f"Page {page.page} of {page.total_pages} ({page.total_results} total)")
        for item in page.items:
            print(item.name)
    """

    items: list[ModelT]
    page: int | None = None
    page_size: int | None = None
    total_pages: int | None = None
    total_results: int | None = None


class NemoPaginatedResponse(Generic[ModelT]):
    """Sync iterable over all items across paginated API responses.

    Lazily fetches subsequent pages using the pagination strategy configured
    on the endpoint's ``Paginated[T, Strategy]`` return type.  Iterating
    yields individual ``ModelT`` items, not page envelopes::

        for item in client.send(list_items()):
            print(item.name)

    For single-page access with metadata, use :meth:`data`::

        page = client.send(list_items()).data()
        print(f"{page.total_results} total across {page.total_pages} pages")
    """

    def __init__(
        self,
        first_http_response: httpx.Response,
        model_type: type[ModelT],
        request: PreparedRequest,
        fetch_page: SyncPageFetcher,
        strategy: type[PaginationStrategy] | None = None,
    ) -> None:
        self._first_response = first_http_response
        self._model_type = model_type
        self.request = request
        self._fetch_page = fetch_page
        self._strategy: type[PaginationStrategy] = strategy or OffsetPagination

    @property
    def http_response(self) -> httpx.Response:
        return self._first_response

    def _parse_page(self, raw: httpx.Response) -> tuple[list[ModelT], dict]:
        """Parse a page response into (items, raw_body)."""
        raw.raise_for_status()
        body = raw.json()
        items = [self._model_type.model_validate(item) for item in self._strategy.extract_items(body)]
        return items, body

    def data(self) -> PageResult[ModelT]:
        """Return the first page as a :class:`PageResult` with metadata."""
        items, body = self._parse_page(self._first_response)
        metadata = self._strategy.extract_metadata(body)
        return PageResult(items=items, **metadata)

    def __iter__(self) -> Iterator[ModelT]:
        items, body = self._parse_page(self._first_response)
        yield from items

        next_page = self._strategy.next_page(body, 1)
        while next_page is not None:
            items, body = self._parse_page(self._fetch_page(self.request, next_page))
            yield from items
            current = next_page
            next_page = self._strategy.next_page(body, current)


class AsyncNemoPaginatedResponse(Generic[ModelT]):
    """Async iterable over all items across paginated API responses.

    Async twin of :class:`NemoPaginatedResponse`::

        async for item in await client.send(list_items()):
            print(item.name)
    """

    def __init__(
        self,
        first_http_response: httpx.Response,
        model_type: type[ModelT],
        request: PreparedRequest,
        fetch_page: AsyncPageFetcher,
        strategy: type[PaginationStrategy] | None = None,
    ) -> None:
        self._first_response = first_http_response
        self._model_type = model_type
        self.request = request
        self._fetch_page = fetch_page
        self._strategy: type[PaginationStrategy] = strategy or OffsetPagination

    @property
    def http_response(self) -> httpx.Response:
        return self._first_response

    def _parse_page(self, raw: httpx.Response) -> tuple[list[ModelT], dict]:
        """Parse a page response into (items, raw_body)."""
        raw.raise_for_status()
        body = raw.json()
        items = [self._model_type.model_validate(item) for item in self._strategy.extract_items(body)]
        return items, body

    def data(self) -> PageResult[ModelT]:
        """Return the first page as a :class:`PageResult` with metadata."""
        items, body = self._parse_page(self._first_response)
        metadata = self._strategy.extract_metadata(body)
        return PageResult(items=items, **metadata)

    async def __aiter__(self) -> AsyncIterator[ModelT]:
        items, body = self._parse_page(self._first_response)
        for item in items:
            yield item

        next_page = self._strategy.next_page(body, 1)
        while next_page is not None:
            raw = await self._fetch_page(self.request, next_page)
            items, body = self._parse_page(raw)
            for item in items:
                yield item
            current = next_page
            next_page = self._strategy.next_page(body, current)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NemoHTTPError(Exception):
    """Raised by :meth:`NemoResponse.data` on non-2xx responses.

    Attributes:
        http_response: The raw httpx response.
        status_code: The HTTP status code.
        detail: A human-readable error message extracted from the response
            body (``{"detail": "..."}`` convention used by FastAPI / NeMo
            Platform), or the raw response text as a fallback.
    """

    def __init__(self, http_response: httpx.Response) -> None:
        self.http_response = http_response
        self.status_code = http_response.status_code
        self.detail = self._extract_detail(http_response)
        super().__init__(f"HTTP {self.status_code}: {self.detail}")

    @staticmethod
    def _extract_detail(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                return body["detail"]
        except Exception:
            pass
        return resp.text
