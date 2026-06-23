# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions using ParamSpec-based decorators.

Endpoints are declared as decorated function signatures. The function's
return type annotation becomes the response type, and its parameters
become the call signature for ``client.call()``::

    @post("/apis/example/v2/workspaces/{workspace}/items")
    def CreateItemEndpoint(body: CreateItemRequest, *, workspace: str) -> Item: ...

    @get("/apis/example/hello/{name}")
    def HelloEndpoint(*, name: str) -> HelloResponse: ...

    client = NemoClient(base_url="http://localhost:8080")
    item = client.call(CreateItemEndpoint, CreateItemRequest(name="x"), workspace="default").data()
    hello = client.call(HelloEndpoint, name="alice").data()

The lower-level ``prepare_request`` + ``send`` API is also available::

    req = CreateItemEndpoint.prepare_request(CreateItemRequest(name="x"), workspace="default")
    resp = client.send(req)

Parameter conventions:
- ``body`` — JSON request body (Pydantic model, serialized automatically)
- ``content`` — binary request body (raw bytes)
- ``query_params`` — query parameters (dict or TypedDict)
- All other keyword parameters — path parameters (matched to ``{placeholders}`` in the path template)
"""

from __future__ import annotations

import inspect
import string
from collections.abc import AsyncIterable, Callable, Iterable
from typing import Generic, get_type_hints

from nemo_platform_plugin.client.types import (
    P,
    PreparedRequest,
    ResponseT,
)
from pydantic import BaseModel


class Endpoint(Generic[P, ResponseT]):
    """A typed HTTP endpoint definition.

    Captures the HTTP method, path template, response type, and the
    call signature (via ``ParamSpec``) from the decorated function.

    Use ``prepare_request()`` to build a :class:`PreparedRequest`, or
    pass this endpoint to ``NemoClient.call()`` for a one-step call.
    """

    def __init__(
        self,
        method: str,
        path: str,
        fn: Callable[P, ResponseT],
    ) -> None:
        self.method = method
        self.path = path
        self._sig = inspect.signature(fn)
        self._path_params = {field_name for _, field_name, _, _ in string.Formatter().parse(path) if field_name}

        hints = get_type_hints(fn)
        ret = hints.get("return")
        self.response_type: type[ResponseT] | None = ret if ret is not None and ret is not type(None) else None

    def prepare_request(self, *args: P.args, **kwargs: P.kwargs) -> PreparedRequest[ResponseT]:
        """Build a :class:`PreparedRequest` by binding the call arguments."""
        bound = self._sig.bind(*args, **kwargs)
        bound.apply_defaults()

        path_params: dict[str, str] = {}
        query_params: dict[str, str | int | bool | None] | None = None
        content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None = None
        content_type: str | None = None

        for name, value in bound.arguments.items():
            if name in self._path_params:
                path_params[name] = str(value)
            elif name == "body":
                assert isinstance(value, BaseModel)
                content = value.model_dump_json().encode()
                content_type = "application/json"
            elif name == "content":
                content = value
                content_type = "application/octet-stream"
            elif name == "query_params":
                if value is not None:
                    query_params = dict(value)

        return PreparedRequest(
            path_template=self.path,
            path_params=path_params,
            method=self.method,
            content=content,
            content_type=content_type,
            response_type=self.response_type,
            query_params=query_params,
        )

    def __repr__(self) -> str:
        resp = self.response_type.__name__ if self.response_type else "None"
        return f"Endpoint({self.method} {self.path} -> {resp})"


# ---------------------------------------------------------------------------
# Decorator factories
# ---------------------------------------------------------------------------


def get(path: str) -> Callable[[Callable[P, ResponseT]], Endpoint[P, ResponseT]]:
    """Define a GET endpoint (no request body)."""

    def decorator(fn: Callable[P, ResponseT]) -> Endpoint[P, ResponseT]:
        return Endpoint(method="GET", path=path, fn=fn)

    return decorator


def post(path: str) -> Callable[[Callable[P, ResponseT]], Endpoint[P, ResponseT]]:
    """Define a POST endpoint."""

    def decorator(fn: Callable[P, ResponseT]) -> Endpoint[P, ResponseT]:
        return Endpoint(method="POST", path=path, fn=fn)

    return decorator


def put(path: str) -> Callable[[Callable[P, ResponseT]], Endpoint[P, ResponseT]]:
    """Define a PUT endpoint."""

    def decorator(fn: Callable[P, ResponseT]) -> Endpoint[P, ResponseT]:
        return Endpoint(method="PUT", path=path, fn=fn)

    return decorator


def patch(path: str) -> Callable[[Callable[P, ResponseT]], Endpoint[P, ResponseT]]:
    """Define a PATCH endpoint."""

    def decorator(fn: Callable[P, ResponseT]) -> Endpoint[P, ResponseT]:
        return Endpoint(method="PATCH", path=path, fn=fn)

    return decorator


def delete(path: str) -> Callable[[Callable[P, ResponseT]], Endpoint[P, ResponseT]]:
    """Define a DELETE endpoint (no request body, optional response body)."""

    def decorator(fn: Callable[P, ResponseT]) -> Endpoint[P, ResponseT]:
        return Endpoint(method="DELETE", path=path, fn=fn)

    return decorator
