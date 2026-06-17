# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions that link request models to response models.

Endpoint objects are the single source of truth for the HTTP contract between
client and server.  Request and response models stay plain Pydantic — the
endpoint carries the type linkage, not the models themselves.

Endpoints are also descriptors: when assigned as class attributes on a
:class:`NemoClient` or :class:`AsyncNemoClient` subclass, accessing them
returns a bound callable that sends the request and returns the typed response.

Define endpoints once in a mixin, then create sync and async client classes::

    class _ItemEndpoints:
        create = post("/items", path_type=WorkspacePath, request_type=CreateItemRequest, response_type=ItemResponse)
        get_item = get("/items/{name}", path_type=WorkspaceItemPath, response_type=ItemResponse)

    class ItemsClient(_ItemEndpoints, NemoClient):
        pass

    class AsyncItemsClient(_ItemEndpoints, AsyncNemoClient):
        pass
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from typing import Generic, Unpack, overload

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.response import (
    AsyncNemoBinaryResponse,
    AsyncNemoStreamResponse,
    NemoBinaryResponse,
    NemoResponse,
    NemoStreamResponse,
)
from nemo_platform_plugin.client.types import (
    BinaryContent,
    ModelT,
    PathT,
    PreparedRequest,
    RequestT,
    ResponseT,
    ResponseT_JSON,
    Stream,
)

# ---------------------------------------------------------------------------
# Sync bound callables
# ---------------------------------------------------------------------------


class SyncBoundBodyCall(Generic[PathT, RequestT, ResponseT]):
    """Sync callable returned when a :class:`BodyEndpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, endpoint: BodyEndpoint[PathT, RequestT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, BinaryContent], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, Stream[ModelT]], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, None], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[None]: ...
    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, ResponseT_JSON], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    def __call__(
        self, payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._endpoint.request(payload, **kw))


class SyncBoundBinaryBodyCall(Generic[PathT, ResponseT]):
    """Sync callable returned when a :class:`BinaryBodyEndpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, endpoint: BinaryBodyEndpoint[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, BinaryContent],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, Stream[ModelT]],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, None],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[None]: ...
    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, ResponseT_JSON],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[ResponseT_JSON]: ...

    def __call__(
        self, content: bytes | Iterable[bytes] | AsyncIterable[bytes], **kw: Unpack[PathT]
    ) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._endpoint.request(content, **kw))


class SyncBoundNoBodyCall(Generic[PathT, ResponseT]):
    """Sync callable returned when a :class:`NoBodyEndpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, endpoint: NoBodyEndpoint[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    def __call__(self: SyncBoundNoBodyCall[PathT, BinaryContent], **kw: Unpack[PathT]) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundNoBodyCall[PathT, Stream[ModelT]], **kw: Unpack[PathT]
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(self: SyncBoundNoBodyCall[PathT, None], **kw: Unpack[PathT]) -> NemoResponse[None]: ...
    @overload
    def __call__(
        self: SyncBoundNoBodyCall[PathT, ResponseT_JSON], **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    def __call__(self, **kw: Unpack[PathT]) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._endpoint.request(**kw))


# ---------------------------------------------------------------------------
# Async bound callables
# ---------------------------------------------------------------------------


class AsyncBoundBodyCall(Generic[PathT, RequestT, ResponseT]):
    """Async callable returned when a :class:`BodyEndpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, endpoint: BodyEndpoint[PathT, RequestT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, BinaryContent], payload: RequestT, **kw: Unpack[PathT]
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, Stream[ModelT]], payload: RequestT, **kw: Unpack[PathT]
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, None], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[None]: ...
    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, ResponseT_JSON], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    async def __call__(
        self, payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._endpoint.request(payload, **kw))


class AsyncBoundBinaryBodyCall(Generic[PathT, ResponseT]):
    """Async callable returned when a :class:`BinaryBodyEndpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, endpoint: BinaryBodyEndpoint[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, BinaryContent],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, Stream[ModelT]],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, None],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[None]: ...
    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, ResponseT_JSON],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[ResponseT_JSON]: ...

    async def __call__(
        self, content: bytes | Iterable[bytes] | AsyncIterable[bytes], **kw: Unpack[PathT]
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._endpoint.request(content, **kw))


class AsyncBoundNoBodyCall(Generic[PathT, ResponseT]):
    """Async callable returned when a :class:`NoBodyEndpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, endpoint: NoBodyEndpoint[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    async def __call__(
        self: AsyncBoundNoBodyCall[PathT, BinaryContent], **kw: Unpack[PathT]
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundNoBodyCall[PathT, Stream[ModelT]], **kw: Unpack[PathT]
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(self: AsyncBoundNoBodyCall[PathT, None], **kw: Unpack[PathT]) -> NemoResponse[None]: ...
    @overload
    async def __call__(
        self: AsyncBoundNoBodyCall[PathT, ResponseT_JSON], **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    async def __call__(self, **kw: Unpack[PathT]) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._endpoint.request(**kw))


# ---------------------------------------------------------------------------
# Endpoint types — descriptors that dispatch sync/async
# ---------------------------------------------------------------------------


class BodyEndpoint(Generic[PathT, RequestT, ResponseT]):
    """Endpoint that requires a JSON request body (POST, PATCH, PUT)."""

    def __init__(
        self, path: str, method: str, request_type: type[RequestT], response_type: type[ResponseT] | None
    ) -> None:
        self.path = path
        self.method = method
        self.request_type = request_type
        self.response_type = response_type

    def request(self, payload: RequestT, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` from a required payload and path parameters."""
        return PreparedRequest(
            path_template=self.path,
            path_params=dict(path_params),
            method=self.method,
            content=payload.model_dump_json().encode(),
            content_type="application/json",
            response_type=self.response_type,
        )

    @overload
    def __get__(
        self, obj: NemoClient, objtype: type | None = None
    ) -> SyncBoundBodyCall[PathT, RequestT, ResponseT]: ...
    @overload
    def __get__(
        self, obj: AsyncNemoClient, objtype: type | None = None
    ) -> AsyncBoundBodyCall[PathT, RequestT, ResponseT]: ...

    def __get__(
        self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None
    ) -> SyncBoundBodyCall[PathT, RequestT, ResponseT] | AsyncBoundBodyCall[PathT, RequestT, ResponseT]:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):
            return AsyncBoundBodyCall(obj, self)
        return SyncBoundBodyCall(obj, self)

    def __repr__(self) -> str:
        return f"BodyEndpoint({self.method} {self.path}, {self.request_type.__name__} -> {self.response_type.__name__ if self.response_type else 'None'})"


class BinaryBodyEndpoint(Generic[PathT, ResponseT]):
    """Endpoint that requires a binary request body (file upload)."""

    def __init__(self, path: str, method: str, response_type: type[ResponseT] | None) -> None:
        self.path = path
        self.method = method
        self.response_type = response_type

    def request(
        self, content: bytes | Iterable[bytes] | AsyncIterable[bytes], **path_params: Unpack[PathT]
    ) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` from binary content and path parameters."""
        return PreparedRequest(
            path_template=self.path,
            path_params=dict(path_params),
            method=self.method,
            content=content,
            content_type="application/octet-stream",
            response_type=self.response_type,
        )

    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> SyncBoundBinaryBodyCall[PathT, ResponseT]: ...
    @overload
    def __get__(
        self, obj: AsyncNemoClient, objtype: type | None = None
    ) -> AsyncBoundBinaryBodyCall[PathT, ResponseT]: ...

    def __get__(
        self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None
    ) -> SyncBoundBinaryBodyCall[PathT, ResponseT] | AsyncBoundBinaryBodyCall[PathT, ResponseT]:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):
            return AsyncBoundBinaryBodyCall(obj, self)
        return SyncBoundBinaryBodyCall(obj, self)

    def __repr__(self) -> str:
        return f"BinaryBodyEndpoint({self.method} {self.path} -> {self.response_type.__name__ if self.response_type else 'None'})"


class NoBodyEndpoint(Generic[PathT, ResponseT]):
    """Endpoint with no request body (GET, DELETE)."""

    def __init__(self, path: str, method: str, response_type: type[ResponseT] | None) -> None:
        self.path = path
        self.method = method
        self.response_type = response_type

    def request(self, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` from path parameters only."""
        return PreparedRequest(
            path_template=self.path,
            path_params=dict(path_params),
            method=self.method,
            content=None,
            content_type=None,
            response_type=self.response_type,
        )

    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> SyncBoundNoBodyCall[PathT, ResponseT]: ...
    @overload
    def __get__(self, obj: AsyncNemoClient, objtype: type | None = None) -> AsyncBoundNoBodyCall[PathT, ResponseT]: ...

    def __get__(
        self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None
    ) -> SyncBoundNoBodyCall[PathT, ResponseT] | AsyncBoundNoBodyCall[PathT, ResponseT]:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):
            return AsyncBoundNoBodyCall(obj, self)
        return SyncBoundNoBodyCall(obj, self)

    def __repr__(self) -> str:
        return f"NoBodyEndpoint({self.method} {self.path} -> {self.response_type.__name__ if self.response_type else 'None'})"


# Union type for use in type hints that accept any endpoint
Endpoint = BodyEndpoint | BinaryBodyEndpoint | NoBodyEndpoint


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def get(path: str, path_type: type[PathT], response_type: type[ResponseT]) -> NoBodyEndpoint[PathT, ResponseT]:
    """Define a GET endpoint (no request body)."""
    return NoBodyEndpoint(path, "GET", response_type)


@overload
def post(
    path: str, path_type: type[PathT], request_type: type[BinaryContent], response_type: type[ResponseT]
) -> BinaryBodyEndpoint[PathT, ResponseT]: ...
@overload
def post(
    path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]
) -> BodyEndpoint[PathT, RequestT, ResponseT]: ...


def post(
    path: str,
    path_type: type[PathT],
    request_type: type[RequestT] | type[BinaryContent],
    response_type: type[ResponseT] | None = None,
) -> BodyEndpoint | BinaryBodyEndpoint:
    """Define a POST endpoint. Pass ``BinaryContent`` as ``request_type`` for binary uploads."""
    if request_type is BinaryContent:
        return BinaryBodyEndpoint(path, "POST", response_type)
    return BodyEndpoint(path, "POST", request_type, response_type)


@overload
def put(
    path: str, path_type: type[PathT], request_type: type[BinaryContent], response_type: type[ResponseT]
) -> BinaryBodyEndpoint[PathT, ResponseT]: ...
@overload
def put(
    path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]
) -> BodyEndpoint[PathT, RequestT, ResponseT]: ...


def put(
    path: str,
    path_type: type[PathT],
    request_type: type[RequestT] | type[BinaryContent],
    response_type: type[ResponseT] | None = None,
) -> BodyEndpoint | BinaryBodyEndpoint:
    """Define a PUT endpoint. Pass ``BinaryContent`` as ``request_type`` for binary uploads."""
    if request_type is BinaryContent:
        return BinaryBodyEndpoint(path, "PUT", response_type)
    return BodyEndpoint(path, "PUT", request_type, response_type)


@overload
def patch(
    path: str, path_type: type[PathT], request_type: type[BinaryContent], response_type: type[ResponseT]
) -> BinaryBodyEndpoint[PathT, ResponseT]: ...
@overload
def patch(
    path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]
) -> BodyEndpoint[PathT, RequestT, ResponseT]: ...


def patch(
    path: str,
    path_type: type[PathT],
    request_type: type[RequestT] | type[BinaryContent],
    response_type: type[ResponseT] | None = None,
) -> BodyEndpoint | BinaryBodyEndpoint:
    """Define a PATCH endpoint. Pass ``BinaryContent`` as ``request_type`` for binary uploads."""
    if request_type is BinaryContent:
        return BinaryBodyEndpoint(path, "PATCH", response_type)
    return BodyEndpoint(path, "PATCH", request_type, response_type)


def delete(path: str, path_type: type[PathT]) -> NoBodyEndpoint[PathT, None]:
    """Define a DELETE endpoint (no request body, no response body)."""
    return NoBodyEndpoint(path, "DELETE", None)
