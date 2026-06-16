# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP response wrappers for JSON, binary, and streaming endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel

ResponseT = TypeVar("ResponseT", bound=BaseModel | None)
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class NemoResponse(Generic[ResponseT]):
    """Typed HTTP response for JSON endpoints.

    Example::

        resp = client.send(GetUserEndpoint.request(workspace="default"))
        resp.body             # UserResponse
        resp.http_response    # full httpx.Response

        user = resp.data()    # raises on non-2xx, otherwise returns body
    """

    http_response: httpx.Response
    body: ResponseT

    def data(self) -> ResponseT:
        """Return the body if the status is 2xx, otherwise raise."""
        if not (200 <= self.http_response.status_code < 300):
            raise NemoHTTPError(self.http_response, self.body)
        return self.body


# ---------------------------------------------------------------------------
# Sync streaming responses
# ---------------------------------------------------------------------------


class NemoBinaryResponse:
    """Sync response for binary download endpoints.

    Example::

        with client.send(DownloadEndpoint.request(...)) as resp:
            for chunk in resp:
                f.write(chunk)
    """

    def __init__(self, http_response: httpx.Response) -> None:
        self.http_response = http_response

    def __iter__(self) -> Iterator[bytes]:
        return self.http_response.iter_bytes()

    def close(self) -> None:
        self.http_response.close()

    def __enter__(self) -> NemoBinaryResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class NemoStreamResponse(Generic[ModelT]):
    """Sync response for SSE/NDJSON streaming endpoints.

    Example::

        with client.send(ChatEndpoint.request(...)) as resp:
            for chunk in resp:
                print(chunk.text)
    """

    def __init__(self, http_response: httpx.Response, model_type: type[ModelT]) -> None:
        self.http_response = http_response
        self._model_type = model_type

    def __iter__(self) -> Iterator[ModelT]:
        for line in self.http_response.iter_lines():
            line = line.strip()
            if line:
                yield self._model_type.model_validate_json(line)

    def close(self) -> None:
        self.http_response.close()

    def __enter__(self) -> NemoStreamResponse[ModelT]:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Async streaming responses
# ---------------------------------------------------------------------------


class AsyncNemoBinaryResponse:
    """Async response for binary download endpoints.

    Example::

        async with client.send(DownloadEndpoint.request(...)) as resp:
            async for chunk in resp:
                f.write(chunk)
    """

    def __init__(self, http_response: httpx.Response) -> None:
        self.http_response = http_response

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.http_response.aiter_bytes():
            yield chunk

    async def close(self) -> None:
        await self.http_response.aclose()

    async def __aenter__(self) -> AsyncNemoBinaryResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


class AsyncNemoStreamResponse(Generic[ModelT]):
    """Async response for SSE/NDJSON streaming endpoints.

    Example::

        async with client.send(ChatEndpoint.request(...)) as resp:
            async for chunk in resp:
                print(chunk.text)
    """

    def __init__(self, http_response: httpx.Response, model_type: type[ModelT]) -> None:
        self.http_response = http_response
        self._model_type = model_type

    async def __aiter__(self) -> AsyncIterator[ModelT]:
        async for line in self.http_response.aiter_lines():
            line = line.strip()
            if line:
                yield self._model_type.model_validate_json(line)

    async def close(self) -> None:
        await self.http_response.aclose()

    async def __aenter__(self) -> AsyncNemoStreamResponse[ModelT]:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NemoHTTPError(Exception):
    """Raised by :meth:`NemoResponse.data` on non-2xx responses."""

    def __init__(self, http_response: httpx.Response, body: object) -> None:
        self.http_response = http_response
        self.body = body
        super().__init__(f"HTTP {http_response.status_code}")
