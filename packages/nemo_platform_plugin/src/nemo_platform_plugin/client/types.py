# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared types for the NeMo client infrastructure.

This module contains marker types, TypeVars, and data classes that are
used across the client package.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass, replace
from typing import Generic, ParamSpec, TypeVar

from pydantic import BaseModel

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

    def with_headers(self, headers: dict[str, str]) -> PreparedRequest[ResponseT]:
        """Return a new PreparedRequest with additional headers merged in."""
        merged = {**(self.extra_headers or {}), **headers}
        return replace(self, extra_headers=merged)
