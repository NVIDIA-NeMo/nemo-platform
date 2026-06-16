# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions that link request models to response models.

Endpoint objects are the single source of truth for the HTTP contract between
client and server.  Request and response models stay plain Pydantic — the
endpoint carries the type linkage, not the models themselves.

Usage::

    from pydantic import BaseModel
    from nemo_platform_plugin.client.endpoint import get, post

    class CreateUserRequest(BaseModel):
        name: str

    class UserResponse(BaseModel):
        name: str
        id: int

    class WorkspacePath(TypedDict):
        workspace: str

    CreateUserEndpoint = post(
        "/v2/workspaces/{workspace}/users",
        WorkspacePath,
        CreateUserRequest,
        UserResponse,
    )

    # Client usage — full type inference on both response and path params:
    resp = client.send(CreateUserEndpoint.request(CreateUserRequest(name="alice"), workspace="default"))
    resp.body  # UserResponse
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from typing import Generic, TypedDict, TypeVar, Unpack, overload

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)

# Type alias for binary content accepted by upload endpoints.
BinaryContent = bytes | Iterable[bytes] | AsyncIterable[bytes]


class BinaryUpload:
    """Marker type: endpoint accepts binary content (file upload)."""


class BinaryStream:
    """Marker type: endpoint returns raw bytes (e.g. file download)."""


class Stream(Generic[ModelT]):
    """Marker type: endpoint returns a stream of ``ModelT`` objects (SSE/NDJSON).

    Used as ``response_type`` in endpoint definitions::

        ChatEndpoint = post("/chat/{workspace}", WorkspacePath, ChatRequest, Stream[ChatChunk])
    """


class BasePath(TypedDict):
    """Base class for all path parameter types.

    All path TypedDicts must inherit from this so that ``PathT`` is
    properly constrained.
    """


PathT = TypeVar("PathT", bound=BasePath)
RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel | BinaryStream | Stream | None)


@dataclass(frozen=True, slots=True)
class PreparedRequest(Generic[ResponseT]):
    """A request ready to be sent — carries the endpoint metadata and payload.

    Created by calling ``request()`` on an endpoint.  The type parameter
    ``ResponseT`` flows through to :meth:`NemoClient.send` so the return type
    is inferred automatically.

    Path interpolation is deferred to the client's ``send()`` method, which
    merges client-level defaults (e.g. workspace) with the explicit path
    params before formatting.
    """

    path_template: str
    path_params: dict[str, str]
    method: str
    content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None
    content_type: str | None
    response_type: type[ResponseT] | None


@dataclass(frozen=True, slots=True)
class BodyEndpoint(Generic[PathT, RequestT, ResponseT]):
    """Endpoint that requires a JSON request body (POST, PATCH, PUT)."""

    path: str
    method: str
    request_type: type[RequestT]
    response_type: type[ResponseT] | None

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


@dataclass(frozen=True, slots=True)
class BinaryBodyEndpoint(Generic[PathT, ResponseT]):
    """Endpoint that requires a binary request body (file upload)."""

    path: str
    method: str
    response_type: type[ResponseT] | None

    def request(self, content: BinaryContent, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` from binary content and path parameters."""
        return PreparedRequest(
            path_template=self.path,
            path_params=dict(path_params),
            method=self.method,
            content=content,
            content_type="application/octet-stream",
            response_type=self.response_type,
        )


@dataclass(frozen=True, slots=True)
class NoBodyEndpoint(Generic[PathT, ResponseT]):
    """Endpoint with no request body (GET, DELETE)."""

    path: str
    method: str
    response_type: type[ResponseT] | None

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


# Union type for use in type hints that accept any endpoint
Endpoint = BodyEndpoint | BinaryBodyEndpoint | NoBodyEndpoint


def get(path: str, path_type: type[PathT], response_type: type[ResponseT]) -> NoBodyEndpoint[PathT, ResponseT]:
    """Define a GET endpoint (no request body)."""
    return NoBodyEndpoint(path, "GET", response_type)


@overload
def post(path: str, path_type: type[PathT], request_type: type[BinaryUpload], response_type: type[ResponseT]) -> BinaryBodyEndpoint[PathT, ResponseT]: ...
@overload
def post(path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> BodyEndpoint[PathT, RequestT, ResponseT]: ...

def post(path: str, path_type: type[PathT], request_type: type[RequestT] | type[BinaryUpload], response_type: type[ResponseT] | None = None) -> BodyEndpoint | BinaryBodyEndpoint:
    """Define a POST endpoint. Pass ``BinaryUpload`` as ``request_type`` for binary uploads."""
    if request_type is BinaryUpload:
        return BinaryBodyEndpoint(path, "POST", response_type)
    return BodyEndpoint(path, "POST", request_type, response_type)


@overload
def put(path: str, path_type: type[PathT], request_type: type[BinaryUpload], response_type: type[ResponseT]) -> BinaryBodyEndpoint[PathT, ResponseT]: ...
@overload
def put(path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> BodyEndpoint[PathT, RequestT, ResponseT]: ...

def put(path: str, path_type: type[PathT], request_type: type[RequestT] | type[BinaryUpload], response_type: type[ResponseT] | None = None) -> BodyEndpoint | BinaryBodyEndpoint:
    """Define a PUT endpoint. Pass ``BinaryUpload`` as ``request_type`` for binary uploads."""
    if request_type is BinaryUpload:
        return BinaryBodyEndpoint(path, "PUT", response_type)
    return BodyEndpoint(path, "PUT", request_type, response_type)


@overload
def patch(path: str, path_type: type[PathT], request_type: type[BinaryUpload], response_type: type[ResponseT]) -> BinaryBodyEndpoint[PathT, ResponseT]: ...
@overload
def patch(path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> BodyEndpoint[PathT, RequestT, ResponseT]: ...

def patch(path: str, path_type: type[PathT], request_type: type[RequestT] | type[BinaryUpload], response_type: type[ResponseT] | None = None) -> BodyEndpoint | BinaryBodyEndpoint:
    """Define a PATCH endpoint. Pass ``BinaryUpload`` as ``request_type`` for binary uploads."""
    if request_type is BinaryUpload:
        return BinaryBodyEndpoint(path, "PATCH", response_type)
    return BodyEndpoint(path, "PATCH", request_type, response_type)


def delete(path: str, path_type: type[PathT]) -> NoBodyEndpoint[PathT, None]:
    """Define a DELETE endpoint (no request body, no response body)."""
    return NoBodyEndpoint(path, "DELETE", None)
