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

from dataclasses import dataclass
from typing import Generic, TypeVar, Unpack

from pydantic import BaseModel

PathT = TypeVar("PathT")
RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT")  # unbound — BaseModel, None, BinaryStream, Stream[T]
ModelT = TypeVar("ModelT", bound=BaseModel)


class BinaryStream:
    """Marker type: endpoint returns raw bytes (e.g. file download)."""


@dataclass(frozen=True, slots=True)
class Stream(Generic[ModelT]):
    """Marker type: endpoint returns a stream of ``ModelT`` objects (SSE/NDJSON).

    Used as ``response_type`` in endpoint definitions::

        ChatEndpoint = post("/chat/{workspace}", WorkspacePath, ChatRequest, Stream[ChatChunk])
    """

    model_type: type[ModelT]


@dataclass(frozen=True, slots=True)
class PreparedRequest(Generic[ResponseT]):
    """A request ready to be sent — carries the endpoint metadata and payload.

    Created by calling ``request()`` on an endpoint.  The type parameter
    ``ResponseT`` flows through to :meth:`NemoClient.send` so the return type
    is inferred automatically.
    """

    path: str
    method: str
    body: BaseModel | None
    response_type: type[ResponseT] | None


@dataclass(frozen=True, slots=True)
class BodyEndpoint(Generic[PathT, RequestT, ResponseT]):
    """Endpoint that requires a request body (POST, PATCH, PUT)."""

    path: str
    method: str
    request_type: type[RequestT]
    response_type: type[ResponseT] | None

    def request(self, payload: RequestT, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` from a required payload and path parameters."""
        resolved_path = self.path.format_map(path_params) if path_params else self.path
        return PreparedRequest(
            path=resolved_path,
            method=self.method,
            body=payload,
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
        resolved_path = self.path.format_map(path_params) if path_params else self.path
        return PreparedRequest(
            path=resolved_path,
            method=self.method,
            body=None,
            response_type=self.response_type,
        )


# Union type for use in type hints that accept any endpoint
Endpoint = BodyEndpoint | NoBodyEndpoint


def get(path: str, path_type: type[PathT], response_type: type[ResponseT]) -> NoBodyEndpoint[PathT, ResponseT]:
    """Define a GET endpoint (no request body)."""
    return NoBodyEndpoint(path, "GET", response_type)


def post(path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> BodyEndpoint[PathT, RequestT, ResponseT]:
    """Define a POST endpoint."""
    return BodyEndpoint(path, "POST", request_type, response_type)


def patch(path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> BodyEndpoint[PathT, RequestT, ResponseT]:
    """Define a PATCH endpoint."""
    return BodyEndpoint(path, "PATCH", request_type, response_type)


def delete(path: str, path_type: type[PathT]) -> NoBodyEndpoint[PathT, None]:
    """Define a DELETE endpoint (no request body, no response body)."""
    return NoBodyEndpoint(path, "DELETE", None)
