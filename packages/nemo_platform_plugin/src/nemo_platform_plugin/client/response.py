# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP response wrappers for JSON, binary, and streaming endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager, asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx
from nemo_platform_plugin.client.errors import raise_for_status
from nemo_platform_plugin.client.types import OffsetPagination, PaginationStrategy, PreparedRequest
from pydantic import BaseModel


def _parse_stream_line(line: str, headers: httpx.Headers) -> str | None:
    """Extract a JSON payload from a stream line, or ``None`` to skip.

    Handles both NDJSON (pass-through) and SSE framing (strips ``data:``
    prefix, skips non-data fields like ``event:``, ``id:``, comments).
    """
    line = line.strip()
    if not line:
        return None
    if "text/event-stream" in headers.get("content-type", ""):
        if line.startswith("data:"):
            return line[5:].strip()
        return None
    return line


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
        """Return the parsed response body.

        Since ``send()`` raises on non-2xx, this is a convenience accessor
        equivalent to ``.body``.
        """
        return self.body


# ---------------------------------------------------------------------------
# Sync streaming responses
# ---------------------------------------------------------------------------


class NemoBinaryResponse:
    """Sync response for binary download endpoints.

    For simple reads::

        resp = client.send(endpoints.download(...))
        data = resp.read()

    For streaming chunks::

        with resp.stream() as chunks:
            for chunk in chunks:
                f.write(chunk)
    """

    def __init__(self, stream_ctx: AbstractContextManager[httpx.Response], request: PreparedRequest) -> None:
        self._stream_ctx = stream_ctx
        self._http_response: httpx.Response | None = None
        self.request = request

    @property
    def http_response(self) -> httpx.Response:
        """The underlying httpx response. Available after entering ``stream()``."""
        if self._http_response is None:
            raise RuntimeError("http_response is only available inside a stream() context")
        return self._http_response

    def read(self) -> bytes:
        """Read and return the entire response body as bytes."""
        with self._stream_ctx as raw:
            data = raw.read()
            raise_for_status(raw)
            return data

    @contextmanager
    def stream(self, chunk_size: int | None = None) -> Iterator[Iterator[bytes]]:
        """Yield an iterator of raw byte chunks.

        Args:
            chunk_size: Maximum number of bytes per chunk. If None, uses the
                transport's default chunking.

        The underlying httpx response is available as ``http_response``
        after entering the context, e.g. for reading ``Content-Length``::

            with resp.stream() as chunks:
                size = resp.http_response.headers.get("content-length")
                for chunk in chunks:
                    ...
        """
        with self._stream_ctx as raw:
            self._http_response = raw
            raise_for_status(raw)
            yield raw.iter_raw(chunk_size) if chunk_size else raw.iter_raw()


class NemoStreamResponse(Generic[ModelT]):
    """Sync response for SSE/NDJSON streaming endpoints.

    Handles both NDJSON (``application/x-ndjson``) and SSE
    (``text/event-stream``) framing automatically based on the
    response ``Content-Type``.  SSE ``data:`` prefixes are stripped
    before JSON parsing.

    Use via :meth:`stream`::

        with client.send(ChatEndpoint(...)).stream() as chunks:
            for chunk in chunks:
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
        self.request = request

    @contextmanager
    def stream(self) -> Iterator[Iterator[ModelT]]:
        """Yield an iterator of parsed model objects."""
        with self._stream_ctx as raw:
            raise_for_status(raw)

            def _iter() -> Iterator[ModelT]:
                for line in raw.iter_lines():
                    payload = _parse_stream_line(line, raw.headers)
                    if payload is not None:
                        yield self._model_type.model_validate_json(payload)

            yield _iter()


# ---------------------------------------------------------------------------
# Async streaming responses
# ---------------------------------------------------------------------------


class AsyncNemoBinaryResponse:
    """Async response for binary download endpoints.

    For simple reads::

        resp = await client.send(endpoints.download(...))
        data = await resp.read()

    For streaming chunks::

        async with resp.stream() as chunks:
            async for chunk in chunks:
                f.write(chunk)
    """

    def __init__(self, stream_ctx: AbstractAsyncContextManager[httpx.Response], request: PreparedRequest) -> None:
        self._stream_ctx = stream_ctx
        self._http_response: httpx.Response | None = None
        self.request = request

    @property
    def http_response(self) -> httpx.Response:
        """The underlying httpx response. Available after entering ``stream()``."""
        if self._http_response is None:
            raise RuntimeError("http_response is only available inside a stream() context")
        return self._http_response

    async def read(self) -> bytes:
        """Read and return the entire response body as bytes."""
        async with self._stream_ctx as raw:
            data = await raw.aread()
            raise_for_status(raw)
            return data

    @asynccontextmanager
    async def stream(self, chunk_size: int | None = None) -> AsyncIterator[AsyncIterator[bytes]]:
        """Yield an async iterator of raw byte chunks.

        Args:
            chunk_size: Maximum number of bytes per chunk. If None, uses the
                transport's default chunking.

        The underlying httpx response is available as ``http_response``
        after entering the context, e.g. for reading ``Content-Length``::

            async with resp.stream() as chunks:
                size = resp.http_response.headers.get("content-length")
                async for chunk in chunks:
                    ...
        """
        async with self._stream_ctx as raw:
            self._http_response = raw
            raise_for_status(raw)
            yield raw.aiter_raw(chunk_size) if chunk_size else raw.aiter_raw()


class AsyncNemoStreamResponse(Generic[ModelT]):
    """Async response for SSE/NDJSON streaming endpoints.

    Handles both NDJSON and SSE framing automatically based on the
    response ``Content-Type``.  See :class:`NemoStreamResponse` for details.

    Use via :meth:`stream`::

        async with (await client.send(ChatEndpoint(...))).stream() as chunks:
            async for chunk in chunks:
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
        self.request = request

    @asynccontextmanager
    async def stream(self) -> AsyncIterator[AsyncIterator[ModelT]]:
        """Yield an async iterator of parsed model objects."""
        async with self._stream_ctx as raw:
            raise_for_status(raw)

            async def _iter() -> AsyncIterator[ModelT]:
                async for line in raw.aiter_lines():
                    payload = _parse_stream_line(line, raw.headers)
                    if payload is not None:
                        yield self._model_type.model_validate_json(payload)

            yield _iter()


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

    Returned by :meth:`NemoPaginatedResponse.page` for callers who want
    one page at a time rather than auto-iterating all pages::

        resp = client.send(list_items())
        page = resp.page()
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
    """Sync paginated API response.

    Provides two iteration modes::

        # Iterate all items across all pages
        for item in response.items():
            print(item.name)

        # Iterate page by page with metadata
        for page in response.pages():
            print(f"Page {page.page}/{page.total_pages}")
            for item in page.items:
                process(item)

    For single-page access, use :meth:`page`::

        page = response.page()
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
        raise_for_status(raw)
        body = raw.json()
        items = [self._model_type.model_validate(item) for item in self._strategy.extract_items(body)]
        return items, body

    def page(self) -> PageResult[ModelT]:
        """Return the first page as a :class:`PageResult` with metadata."""
        items, body = self._parse_page(self._first_response)
        metadata = self._strategy.extract_metadata(body)
        return PageResult(items=items, **metadata)

    def items(self) -> Iterator[ModelT]:
        """Iterate all items across all pages, fetching subsequent pages lazily."""
        items, body = self._parse_page(self._first_response)
        yield from items

        next_page = self._strategy.next_page(body, 1)
        while next_page is not None:
            items, body = self._parse_page(self._fetch_page(self.request, next_page))
            yield from items
            current = next_page
            next_page = self._strategy.next_page(body, current)

    def pages(self) -> Iterator[PageResult[ModelT]]:
        """Iterate page by page, yielding :class:`PageResult` objects with metadata."""
        items, body = self._parse_page(self._first_response)
        metadata = self._strategy.extract_metadata(body)
        yield PageResult(items=items, **metadata)

        next_page = self._strategy.next_page(body, 1)
        while next_page is not None:
            items, body = self._parse_page(self._fetch_page(self.request, next_page))
            metadata = self._strategy.extract_metadata(body)
            yield PageResult(items=items, **metadata)
            current = next_page
            next_page = self._strategy.next_page(body, current)


class AsyncNemoPaginatedResponse(Generic[ModelT]):
    """Async paginated API response.

    Async twin of :class:`NemoPaginatedResponse`::

        async for item in response.items():
            print(item.name)

        async for page in response.pages():
            print(f"Page {page.page}/{page.total_pages}")
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
        raise_for_status(raw)
        body = raw.json()
        items = [self._model_type.model_validate(item) for item in self._strategy.extract_items(body)]
        return items, body

    def page(self) -> PageResult[ModelT]:
        """Return the first page as a :class:`PageResult` with metadata."""
        items, body = self._parse_page(self._first_response)
        metadata = self._strategy.extract_metadata(body)
        return PageResult(items=items, **metadata)

    async def items(self) -> AsyncIterator[ModelT]:
        """Iterate all items across all pages, fetching subsequent pages lazily."""
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

    async def pages(self) -> AsyncIterator[PageResult[ModelT]]:
        """Iterate page by page, yielding :class:`PageResult` objects with metadata."""
        items, body = self._parse_page(self._first_response)
        metadata = self._strategy.extract_metadata(body)
        yield PageResult(items=items, **metadata)

        next_page = self._strategy.next_page(body, 1)
        while next_page is not None:
            raw = await self._fetch_page(self.request, next_page)
            items, body = self._parse_page(raw)
            metadata = self._strategy.extract_metadata(body)
            yield PageResult(items=items, **metadata)
            current = next_page
            next_page = self._strategy.next_page(body, current)
