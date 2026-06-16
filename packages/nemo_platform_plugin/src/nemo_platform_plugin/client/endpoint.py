# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions that link request models to response models.

Endpoint objects are the single source of truth for the HTTP contract between
client and server.  Request and response models stay plain Pydantic — the
endpoint carries the type linkage, not the models themselves.

Usage::

    from pydantic import BaseModel
    from nemo_platform_plugin.client.endpoint import Endpoint

    class CreateUserRequest(BaseModel):
        name: str

    class UserResponse(BaseModel):
        name: str
        id: int

    class WorkspacePath(TypedDict):
        workspace: str

    CREATE_USER = Endpoint.post(
        "/v2/workspaces/{workspace}/users",
        path_type=WorkspacePath,
        request_type=CreateUserRequest,
        response_type=UserResponse,
    )

    # Client usage — full type inference on both response and path params:
    resp = client.send(CREATE_USER(CreateUserRequest(name="alice"), workspace="default"))
    resp.body  # UserResponse
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, Unpack

from pydantic import BaseModel

PathT = TypeVar("PathT")
RequestT = TypeVar("RequestT", bound=BaseModel | None)
ResponseT = TypeVar("ResponseT", bound=BaseModel | None)


@dataclass(frozen=True, slots=True)
class PreparedRequest(Generic[ResponseT]):
    """A request ready to be sent — carries the endpoint metadata and payload.

    Created by calling an :class:`Endpoint` with a payload.  The type parameter
    ``ResponseT`` flows through to :meth:`NemoClient.send` so the return type
    is inferred automatically.
    """

    path: str
    method: str
    body: BaseModel | None
    response_type: type[ResponseT] | None


@dataclass(frozen=True, slots=True)
class Endpoint(Generic[PathT, RequestT, ResponseT]):
    """A typed HTTP endpoint definition.

    Links a path type ``PathT``, request model ``RequestT``, and response model
    ``ResponseT`` together with the HTTP method and path template.  Calling an
    endpoint with a payload produces a :class:`PreparedRequest` that can be
    passed to the client.

    Parameters
    ----------
    path:
        URL path template, e.g. ``"/v2/workspaces/{workspace}/items"``.
        Path parameters are filled by keyword arguments when calling the endpoint.
    method:
        HTTP method (``GET``, ``POST``, ``PATCH``, ``DELETE``).
    request_type:
        Pydantic model class for the request body (``None`` for body-less methods).
    response_type:
        Pydantic model class for the response body (``None`` for body-less responses).
    """

    path: str
    method: str
    request_type: type[RequestT] | None
    response_type: type[ResponseT] | None

    def request(self, payload: RequestT | None = None, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` from a payload and path parameters.

        Path parameters are substituted into the URL template using
        ``str.format_map``.
        """
        resolved_path = self.path.format_map(path_params) if path_params else self.path
        return PreparedRequest(
            path=resolved_path,
            method=self.method,
            body=payload,
            response_type=self.response_type,
        )

    @classmethod
    def get(cls, path: str, path_type: type[PathT], response_type: type[ResponseT]) -> Endpoint[PathT, None, ResponseT]:
        """Define a GET endpoint (no request body)."""
        return Endpoint(path, "GET", None, response_type)

    @classmethod
    def post(cls, path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> Endpoint[PathT, RequestT, ResponseT]:
        """Define a POST endpoint."""
        return Endpoint(path, "POST", request_type, response_type)

    @classmethod
    def patch(cls, path: str, path_type: type[PathT], request_type: type[RequestT], response_type: type[ResponseT]) -> Endpoint[PathT, RequestT, ResponseT]:
        """Define a PATCH endpoint."""
        return Endpoint(path, "PATCH", request_type, response_type)

    @classmethod
    def delete(cls, path: str, path_type: type[PathT]) -> Endpoint[PathT, None, None]:
        """Define a DELETE endpoint (no request body, no response body)."""
        return Endpoint(path, "DELETE", None, None)
