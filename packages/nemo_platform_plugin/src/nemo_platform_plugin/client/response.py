# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP response wrappers for JSON, binary, and streaming endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Generic, TypeVar

import httpx
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
