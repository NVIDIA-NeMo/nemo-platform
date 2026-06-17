# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions and factory functions.

Endpoints are descriptors: when assigned as class attributes on a
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

from nemo_platform_plugin.client.bound import AsyncBoundCall, SyncBoundCall
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.types import (
    BinaryContent,
    BodyRequestT,
    PathT,
    PreparedRequest,
    RequestT,
    ResponseT,
)
from pydantic import BaseModel


class Endpoint(Generic[PathT, RequestT, ResponseT]):
    """A typed HTTP endpoint definition.

    Links a path type ``PathT``, request type ``RequestT``, and response type
    ``ResponseT`` together with the HTTP method and path template.

    Also a descriptor: when assigned as a class attribute on a
    :class:`NemoClient` or :class:`AsyncNemoClient` subclass, accessing it
    returns a :class:`SyncBoundCall` or :class:`AsyncBoundCall`.
    """

    def __init__(
        self, path: str, method: str, request_type: type[RequestT] | None, response_type: type[ResponseT] | None
    ) -> None:
        self.path = path
        self.method = method
        self.request_type = request_type
        self.response_type = response_type

    # -- request() overloads: body / binary / no-body ----------------------

    @overload
    def request(
        self: Endpoint[PathT, BodyRequestT, ResponseT], payload: BodyRequestT, **path_params: Unpack[PathT]
    ) -> PreparedRequest[ResponseT]: ...
    @overload
    def request(
        self: Endpoint[PathT, BinaryContent, ResponseT],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **path_params: Unpack[PathT],
    ) -> PreparedRequest[ResponseT]: ...
    @overload
    def request(self: Endpoint[PathT, None, ResponseT], **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]: ...

    def request(self, *args: object, **path_params: object) -> PreparedRequest:
        """Build a :class:`PreparedRequest` from payload/content and path parameters."""
        params = {k: str(v) for k, v in path_params.items()}
        content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None
        content_type: str | None

        if self.request_type is None:
            content = None
            content_type = None
        elif self.request_type is BinaryContent:
            content = args[0]  # type: ignore[assignment]
            content_type = "application/octet-stream"
        else:
            payload = args[0]
            assert isinstance(payload, BaseModel)
            content = payload.model_dump_json().encode()
            content_type = "application/json"

        return PreparedRequest(
            path_template=self.path,
            path_params=params,
            method=self.method,
            content=content,
            content_type=content_type,
            response_type=self.response_type,
        )

    # -- Descriptor: sync vs async -----------------------------------------

    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> SyncBoundCall[PathT, RequestT, ResponseT]: ...
    @overload
    def __get__(
        self, obj: AsyncNemoClient, objtype: type | None = None
    ) -> AsyncBoundCall[PathT, RequestT, ResponseT]: ...

    def __get__(
        self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None
    ) -> SyncBoundCall[PathT, RequestT, ResponseT] | AsyncBoundCall[PathT, RequestT, ResponseT]:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):
            return AsyncBoundCall(obj, self.request)
        return SyncBoundCall(obj, self.request)

    def __repr__(self) -> str:
        req = self.request_type.__name__ if self.request_type else "None"
        resp = self.response_type.__name__ if self.response_type else "None"
        return f"Endpoint({self.method} {self.path}, {req} -> {resp})"


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def get(path: str, path_type: type[PathT], response_type: type[ResponseT]) -> Endpoint[PathT, None, ResponseT]:
    """Define a GET endpoint (no request body)."""
    return Endpoint(path, "GET", None, response_type)


def post(
    path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]
) -> Endpoint[PathT, RequestT, ResponseT]:
    """Define a POST endpoint."""
    return Endpoint(path, "POST", request_type, response_type)


def put(
    path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]
) -> Endpoint[PathT, RequestT, ResponseT]:
    """Define a PUT endpoint."""
    return Endpoint(path, "PUT", request_type, response_type)


def patch(
    path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]
) -> Endpoint[PathT, RequestT, ResponseT]:
    """Define a PATCH endpoint."""
    return Endpoint(path, "PATCH", request_type, response_type)


def delete(path: str, path_type: type[PathT]) -> Endpoint[PathT, None, None]:
    """Define a DELETE endpoint (no request body, no response body)."""
    return Endpoint(path, "DELETE", None, None)
