# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions and factory functions.

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

from nemo_platform_plugin.client.bound import (
    AsyncBoundBinaryBodyCall,
    AsyncBoundBodyCall,
    AsyncBoundNoBodyCall,
    SyncBoundBinaryBodyCall,
    SyncBoundBodyCall,
    SyncBoundNoBodyCall,
)
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.types import (
    BinaryContent,
    PathT,
    PreparedRequest,
    RequestT,
    ResponseT,
)

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
