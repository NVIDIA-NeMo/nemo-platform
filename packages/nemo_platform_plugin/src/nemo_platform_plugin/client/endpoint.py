# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions using ParamSpec-based decorators.

Endpoints are declared as decorated methods on a class. The decorator
replaces each method with a callable that builds a :class:`PreparedRequest`,
preserving the original call signature for autocomplete and type checking::

    class ExampleEndpoints:
        @post("/apis/example/v2/workspaces/{workspace}/items")
        def create_item(self, body: CreateItemRequest, *, workspace: str) -> Item:
            raise NotImplementedError

        @get("/apis/example/hello/{name}")
        def hello(self, *, name: str) -> HelloResponse:
            raise NotImplementedError

    endpoints = ExampleEndpoints()
    req = endpoints.create_item(workspace="default", body=CreateItemRequest(name="x"))
    resp = client.send(req)  # NemoResponse[Item]

Parameter conventions:
- ``body`` — JSON request body (Pydantic model, serialized automatically)
- ``content`` — binary request body (raw bytes)
- ``query_params`` — query parameters (dict or TypedDict)
- All other keyword parameters — path parameters (matched to ``{placeholders}`` in the path template)
"""

from __future__ import annotations

import functools
import inspect
import string
from collections.abc import AsyncIterable, Callable, Iterable
from typing import get_type_hints

from nemo_platform_plugin.client.types import (
    P,
    PreparedRequest,
    ResponseT,
)
from pydantic import BaseModel


def _build_prepared_request(
    method: str,
    path: str,
    sig: inspect.Signature,
    path_param_names: set[str],
    response_type: type | None,
    args: tuple,
    kwargs: dict,
) -> PreparedRequest:
    """Build a PreparedRequest by binding call arguments to the endpoint signature.

    Uses ``bind_partial`` so that path parameters with client-level defaults
    (e.g. ``workspace``) can be omitted by the caller.
    """
    bound = sig.bind_partial(*args, **kwargs)
    bound.apply_defaults()

    path_params: dict[str, str] = {}
    query_params: dict[str, str | int | bool | None] | None = None
    content: bytes | Iterable[bytes] | AsyncIterable[bytes] | None = None
    content_type: str | None = None

    for name, value in bound.arguments.items():
        if name == "self":
            continue
        if name in path_param_names:
            if value is not None:
                path_params[name] = str(value)
        elif name == "body":
            if not isinstance(value, BaseModel):
                raise TypeError(f"body must be a BaseModel instance, got {type(value).__name__}")
            content = value.model_dump_json().encode()
            content_type = "application/json"
        elif name == "content":
            content = value
            content_type = "application/octet-stream"
        elif name == "query_params":
            if value is not None:
                query_params = dict(value)

    return PreparedRequest(
        path_template=path,
        path_params=path_params,
        method=method,
        content=content,
        content_type=content_type,
        response_type=response_type,
        query_params=query_params,
    )


def _make_endpoint(http_method: str, path: str, fn: Callable[P, ResponseT]) -> Callable[P, PreparedRequest[ResponseT]]:
    """Create a callable that builds PreparedRequests from the function's signature."""
    sig = inspect.signature(fn)
    path_param_names = {field_name for _, field_name, _, _ in string.Formatter().parse(path) if field_name}
    hints = get_type_hints(fn)
    ret = hints.get("return")
    response_type = ret if ret is not None and ret is not type(None) else None

    @functools.wraps(fn)
    def prepare(*args: P.args, **kwargs: P.kwargs) -> PreparedRequest[ResponseT]:
        return _build_prepared_request(http_method, path, sig, path_param_names, response_type, args, kwargs)

    return prepare


# ---------------------------------------------------------------------------
# Decorator factories
# ---------------------------------------------------------------------------


def get(path: str) -> Callable[[Callable[P, ResponseT]], Callable[P, PreparedRequest[ResponseT]]]:
    """Define a GET endpoint (no request body)."""

    def decorator(fn: Callable[P, ResponseT]) -> Callable[P, PreparedRequest[ResponseT]]:
        return _make_endpoint("GET", path, fn)

    return decorator


def post(path: str) -> Callable[[Callable[P, ResponseT]], Callable[P, PreparedRequest[ResponseT]]]:
    """Define a POST endpoint."""

    def decorator(fn: Callable[P, ResponseT]) -> Callable[P, PreparedRequest[ResponseT]]:
        return _make_endpoint("POST", path, fn)

    return decorator


def put(path: str) -> Callable[[Callable[P, ResponseT]], Callable[P, PreparedRequest[ResponseT]]]:
    """Define a PUT endpoint."""

    def decorator(fn: Callable[P, ResponseT]) -> Callable[P, PreparedRequest[ResponseT]]:
        return _make_endpoint("PUT", path, fn)

    return decorator


def patch(path: str) -> Callable[[Callable[P, ResponseT]], Callable[P, PreparedRequest[ResponseT]]]:
    """Define a PATCH endpoint."""

    def decorator(fn: Callable[P, ResponseT]) -> Callable[P, PreparedRequest[ResponseT]]:
        return _make_endpoint("PATCH", path, fn)

    return decorator


def delete(path: str) -> Callable[[Callable[P, ResponseT]], Callable[P, PreparedRequest[ResponseT]]]:
    """Define a DELETE endpoint (no request body, optional response body)."""

    def decorator(fn: Callable[P, ResponseT]) -> Callable[P, PreparedRequest[ResponseT]]:
        return _make_endpoint("DELETE", path, fn)

    return decorator
