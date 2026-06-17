# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared types for the NeMo client infrastructure.

This module contains marker types, TypeVars, and data classes that are
used by both ``endpoint.py`` and ``client.py``, extracted here to avoid
circular imports.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from typing import Generic, Protocol, TypedDict, TypeVar, Unpack

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)
ResponseT_JSON = TypeVar("ResponseT_JSON", bound=BaseModel | None)


class BinaryContent:
    """Marker type: endpoint sends or receives raw bytes.

    Use as ``request_type`` for binary uploads or ``response_type`` for
    binary downloads::

        UploadEndpoint = put("/files/{path}", path_type=FilePath, request_type=BinaryContent, response_type=FileResponse)
        DownloadEndpoint = get("/files/{path}", path_type=FilePath, response_type=BinaryContent)
    """


class Stream(Generic[ModelT]):
    """Marker type: endpoint returns a stream of ``ModelT`` objects (SSE/NDJSON).

    Used as ``response_type`` in endpoint definitions::

        ChatEndpoint = post("/chat/{workspace}", path_type=WorkspacePath, request_type=ChatRequest, response_type=Stream[ChatChunk])
    """


class BasePath(TypedDict):
    """Base class for all path parameter types.

    All path TypedDicts must inherit from this so that ``PathT`` is
    properly constrained.
    """


PathT = TypeVar("PathT", bound=BasePath)
RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel | BinaryContent | Stream | None)


# ---------------------------------------------------------------------------
# Protocols — what bound callables need from endpoints
# ---------------------------------------------------------------------------


class BodyRequestable(Protocol[PathT, RequestT, ResponseT]):
    """Protocol for endpoints that accept a JSON payload."""

    def request(self, payload: RequestT, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]: ...


class BinaryBodyRequestable(Protocol[PathT, ResponseT]):
    """Protocol for endpoints that accept binary content."""

    def request(
        self, content: bytes | Iterable[bytes] | AsyncIterable[bytes], **path_params: Unpack[PathT]
    ) -> PreparedRequest[ResponseT]: ...


class NoBodyRequestable(Protocol[PathT, ResponseT]):
    """Protocol for endpoints with no request body."""

    def request(self, **path_params: Unpack[PathT]) -> PreparedRequest[ResponseT]: ...


# ---------------------------------------------------------------------------
# PreparedRequest
# ---------------------------------------------------------------------------


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
