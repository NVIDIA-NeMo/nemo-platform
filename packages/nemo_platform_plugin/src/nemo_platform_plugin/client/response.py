# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP response wrappers for JSON, binary, and streaming endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx
from nemo_platform_plugin.client.errors import raise_for_status
from nemo_platform_plugin.client.types import PreparedRequest
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
        """Return the parsed response body.

        Since ``send()`` raises on non-2xx, this is just a convenience
        accessor equivalent to ``.body``.
        """
        return self.body


# ---------------------------------------------------------------------------
# Sync streaming responses
# ---------------------------------------------------------------------------


class NemoBinaryResponse:
    """Sync response for binary download endpoints.

    ``read()`` performs a regular (non-streaming) HTTP request::

        resp = client.send(endpoints.download(...))
        data = resp.read()

    For streaming chunks, use ``stream()`` which returns a context manager
    yielding the raw ``httpx.Response``::

        resp = client.send(endpoints.download(...))
        with resp.stream() as http_response:
            for chunk in http_response.iter_bytes():
                f.write(chunk)
    """

    def __init__(self, http: httpx.Client, request_kwargs: dict[str, Any], request: PreparedRequest) -> None:
        self._http = http
        self._request_kwargs = request_kwargs
        self.request = request

    def read(self) -> bytes:
        """Read and return the entire response body as bytes."""
        resp = self._http.request(**self._request_kwargs)
        raise_for_status(resp)
        return resp.content

    @contextmanager
    def stream(self) -> Iterator[httpx.Response]:
        """Open a streaming connection for chunk-by-chunk iteration."""
        with self._http.stream(**self._request_kwargs) as resp:
            raise_for_status(resp)
            yield resp


class NemoStreamResponse(Generic[ModelT]):
    """Sync response for SSE/NDJSON streaming endpoints.

    Use ``stream()`` to iterate over parsed model objects::

        resp = client.send(ChatEndpoint(...))
        with resp.stream() as chunks:
            for chunk in chunks:
                print(chunk.text)
    """

    def __init__(
        self, http: httpx.Client, request_kwargs: dict[str, Any], model_type: type[ModelT], request: PreparedRequest
    ) -> None:
        self._http = http
        self._request_kwargs = request_kwargs
        self._model_type = model_type
        self.request = request

    @contextmanager
    def stream(self) -> Iterator[Iterator[ModelT]]:
        """Open a streaming connection and yield an iterator of parsed models."""
        with self._http.stream(**self._request_kwargs) as resp:
            raise_for_status(resp)

            def _iter_models() -> Iterator[ModelT]:
                for line in resp.iter_lines():
                    line = line.strip()
                    if line:
                        yield self._model_type.model_validate_json(line)

            yield _iter_models()


# ---------------------------------------------------------------------------
# Async streaming responses
# ---------------------------------------------------------------------------


class AsyncNemoBinaryResponse:
    """Async response for binary download endpoints.

    ``read()`` performs a regular (non-streaming) HTTP request::

        resp = await client.send(endpoints.download(...))
        data = await resp.read()

    For streaming chunks, use ``stream()`` which returns an async context
    manager yielding the raw ``httpx.Response``::

        resp = await client.send(endpoints.download(...))
        async with resp.stream() as http_response:
            async for chunk in http_response.aiter_bytes():
                f.write(chunk)
    """

    def __init__(self, http: httpx.AsyncClient, request_kwargs: dict[str, Any], request: PreparedRequest) -> None:
        self._http = http
        self._request_kwargs = request_kwargs
        self.request = request

    async def read(self) -> bytes:
        """Read and return the entire response body as bytes."""
        resp = await self._http.request(**self._request_kwargs)
        raise_for_status(resp)
        return resp.content

    @asynccontextmanager
    async def stream(self) -> AsyncIterator[httpx.Response]:
        """Open a streaming connection for chunk-by-chunk iteration."""
        async with self._http.stream(**self._request_kwargs) as resp:
            raise_for_status(resp)
            yield resp


class AsyncNemoStreamResponse(Generic[ModelT]):
    """Async response for SSE/NDJSON streaming endpoints.

    Use ``stream()`` to iterate over parsed model objects::

        resp = await client.send(ChatEndpoint(...))
        async with resp.stream() as chunks:
            async for chunk in chunks:
                print(chunk.text)
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        request_kwargs: dict[str, Any],
        model_type: type[ModelT],
        request: PreparedRequest,
    ) -> None:
        self._http = http
        self._request_kwargs = request_kwargs
        self._model_type = model_type
        self.request = request

    @asynccontextmanager
    async def stream(self) -> AsyncIterator[AsyncIterator[ModelT]]:
        """Open a streaming connection and yield an async iterator of parsed models."""
        async with self._http.stream(**self._request_kwargs) as resp:
            raise_for_status(resp)

            async def _iter_models() -> AsyncIterator[ModelT]:
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line:
                        yield self._model_type.model_validate_json(line)

            yield _iter_models()
