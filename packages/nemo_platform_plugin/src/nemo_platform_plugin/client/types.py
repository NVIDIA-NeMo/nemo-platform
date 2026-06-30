# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared types for the NeMo client infrastructure.

This module contains marker types, TypeVars, data classes, pagination
strategies, and client-side option definitions used across the client package.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass, replace
from typing import Any, ClassVar, Generic, ParamSpec, Protocol, TypeVar

from pydantic import BaseModel
from typing_extensions import TypeVar as TypeVarExt

P = ParamSpec("P")
ModelT = TypeVar("ModelT", bound=BaseModel)
ResponseT = TypeVar("ResponseT")


class BinaryContent:
    """Marker type: endpoint sends or receives raw bytes.

    Use ``content`` parameter for binary uploads::

        @put("/files/{path}")
        def UploadEndpoint(content: bytes, *, path: str) -> FileResponse: ...
    """


class Stream(Generic[ModelT]):
    """Marker type: endpoint returns a stream of ``ModelT`` objects (SSE/NDJSON).

    Used as return type in endpoint definitions::

        @post("/chat/{workspace}")
        def ChatEndpoint(body: ChatRequest, *, workspace: str) -> Stream[ChatChunk]: ...
    """


# ---------------------------------------------------------------------------
# Pagination strategies
# ---------------------------------------------------------------------------


class PaginationStrategy(Protocol):
    """Protocol for pagination strategies.

    Pagination strategies control how the client extracts items from a page
    response, determines the next page identifier, builds query params
    to fetch the next page, and extracts pagination metadata.
    """

    @classmethod
    def extract_items(cls, response_body: dict) -> list[dict]: ...

    @classmethod
    def next_page(cls, response_body: dict, current_page: Any) -> Any | None: ...

    @classmethod
    def page_query_params(cls, page: Any) -> dict[str, Any]: ...

    @classmethod
    def extract_metadata(cls, response_body: dict) -> dict[str, Any]: ...


class OffsetPagination:
    """Offset-based pagination using ``page`` query parameter.

    This is the default strategy, matching the standard ``NemoListResponse``
    envelope used by NeMo Platform services::

        {"data": [...], "pagination": {"page": 1, "total_pages": 5, ...}}

    Subclass to customise field names for non-standard envelopes::

        class MyPagination(OffsetPagination):
            items_field = "results"
            page_param = "offset"
    """

    items_field: ClassVar[str] = "data"
    page_param: ClassVar[str] = "page"
    pagination_field: ClassVar[str] = "pagination"
    page_field: ClassVar[str] = "page"
    page_size_field: ClassVar[str] = "page_size"
    total_pages_field: ClassVar[str] = "total_pages"
    total_results_field: ClassVar[str] = "total_results"

    @classmethod
    def extract_items(cls, response_body: dict) -> list[dict]:
        return response_body.get(cls.items_field, [])

    @classmethod
    def next_page(cls, response_body: dict, current_page: int) -> int | None:
        pagination = response_body.get(cls.pagination_field)
        if pagination is None:
            return None
        total = pagination.get(cls.total_pages_field, 1)
        if current_page < total:
            return current_page + 1
        return None

    @classmethod
    def page_query_params(cls, page: int) -> dict[str, int]:
        return {cls.page_param: page}

    @classmethod
    def extract_metadata(cls, response_body: dict) -> dict[str, Any]:
        pagination = response_body.get(cls.pagination_field) or {}
        return {
            "page": pagination.get(cls.page_field),
            "page_size": pagination.get(cls.page_size_field),
            "total_pages": pagination.get(cls.total_pages_field),
            "total_results": pagination.get(cls.total_results_field),
        }


StrategyT = TypeVarExt("StrategyT", default=OffsetPagination)


class Paginated(Generic[ModelT, StrategyT]):
    """Marker type: endpoint returns paginated results of ``ModelT``.

    The second type parameter selects the pagination strategy.  It defaults
    to :class:`OffsetPagination`, which matches the standard
    ``NemoListResponse`` envelope.

    Usage::

        # Default offset-based pagination
        @get("/apis/example/v2/workspaces/{workspace}/items")
        def list_items(...) -> Paginated[Item]: ...

        # Custom strategy
        class MyPagination(OffsetPagination):
            items_field = "results"
            page_param = "offset"

        @get("/apis/example/v2/workspaces/{workspace}/widgets")
        def list_widgets(...) -> Paginated[Widget, MyPagination]: ...

    Caller experience::

        for item in client.list_items():
            print(item.name)
    """


# ---------------------------------------------------------------------------
# Endpoint parameter registries
# ---------------------------------------------------------------------------

# Parameter names with special handling in the endpoint decorator.
# These are routed to specific fields on ``PreparedRequest`` (body, content,
# query_params) and are not treated as path parameters.
RESERVED_PARAM_NAMES: frozenset[str] = frozenset({"self", "body", "content", "query_params"})

# Parameters with these names are recognised in endpoint signatures as
# client-side options.  They are stripped from the HTTP request and stashed
# in ``PreparedRequest.client_options`` for the client to act on.
#
# Each entry maps a parameter name to its expected Python type.
# Unknown parameters in an endpoint signature trigger a ``TypeError``
# at decoration time.
BLESSED_CLIENT_PARAMS: dict[str, type] = {
    "exist_ok": bool,
}


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry transient failures with exponential backoff.

    Set as a client-level default via the ``retry`` constructor parameter,
    or override per-request via ``send()``'s ``retry`` keyword argument.

    This is an operational concern — it does not belong in endpoint
    signatures.

    .. note::

        The retry loop replays the full request including the body.
        Callers are responsible for ensuring idempotency when retrying
        non-safe methods (POST, PATCH).  Consider using an
        ``Idempotency-Key`` header for create operations that must be
        safe to retry.

    Usage::

        # Client-level default
        client = MyClient(base_url="...", retry=RetryPolicy(max_retries=3))

        # Per-request override via send()
        client.send(endpoint_fn(...), retry=RetryPolicy(max_retries=10))
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    retryable_status_codes: tuple[int, ...] = (502, 503, 504, 429)


@dataclass(frozen=True, slots=True)
class PreparedRequest(Generic[ResponseT]):
    """A request ready to be sent — carries the endpoint metadata and payload.

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
    query_params: dict[str, str | int | bool | None] | None = None
    extra_headers: dict[str, str] | None = None
    client_options: dict[str, Any] | None = None

    def with_headers(self, headers: dict[str, str]) -> PreparedRequest[ResponseT]:
        """Return a new PreparedRequest with additional headers merged in."""
        merged = {**(self.extra_headers or {}), **headers}
        return replace(self, extra_headers=merged)
