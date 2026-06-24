# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP client for NeMo Platform.

Sends :class:`~.endpoint.PreparedRequest` objects and returns typed
responses.  The return type of :meth:`send` is determined by the endpoint's
``ResponseT``:

- ``BaseModel`` → :class:`~.response.NemoResponse[T]`
- ``None`` → :class:`~.response.NemoResponse[None]`
- ``BinaryContent`` → :class:`~.response.NemoBinaryResponse`
- ``Stream[T]`` → :class:`~.response.NemoStreamResponse[T]`
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar, get_args, get_origin, overload

import httpx
from nemo_platform_plugin.client.response import (
    AsyncNemoBinaryResponse,
    AsyncNemoStreamResponse,
    NemoBinaryResponse,
    NemoResponse,
    NemoStreamResponse,
)
from nemo_platform_plugin.client.types import BinaryContent, PreparedRequest, ResponseT, Stream
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_TIMEOUT = 60.0


def _get_stream_model_type(response_type: type) -> type[BaseModel]:
    """Extract the ModelT from a Stream[ModelT] generic alias."""
    args = get_args(response_type)
    if not args:
        raise TypeError(f"Stream response type must be parameterized, got {response_type}")
    return args[0]


class BaseNemoClient:
    """Shared logic for sync and async NeMo clients.

    Handles URL construction and request serialisation.
    Subclasses provide the actual HTTP transport (sync or async).
    """

    def __init__(self, *, base_url: str, workspace: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._workspace = workspace

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def workspace(self) -> str | None:
        return self._workspace

    def _resolve_path(self, request: PreparedRequest) -> str:
        """Resolve path template with client defaults and explicit params.

        Client-level defaults (e.g. workspace) are merged under explicit
        params — explicit always wins.  Raises ``ValueError`` if any
        placeholders remain unresolved.
        """
        params: dict[str, str] = {}
        if self._workspace:
            params["workspace"] = self._workspace
        params.update(request.path_params)
        try:
            path = request.path_template.format_map(params)
        except KeyError as exc:
            raise ValueError(f"Missing path parameter {exc} for {request.method} {request.path_template}") from exc
        return self._base_url + path

    def _request_headers(self, request: PreparedRequest) -> dict[str, str] | None:
        headers: dict[str, str] = {}
        if request.content_type is not None:
            headers["Content-Type"] = request.content_type
        if request.extra_headers:
            headers.update(request.extra_headers)
        return headers or None

    def _is_binary(self, request: PreparedRequest) -> bool:
        return request.response_type is BinaryContent

    def _is_stream(self, request: PreparedRequest) -> bool:
        return get_origin(request.response_type) is Stream

    def _resolve_query_params(self, request: PreparedRequest) -> dict[str, str | int | bool] | None:
        """Filter out None values from query params for httpx."""
        if request.query_params is None:
            return None
        filtered = {k: v for k, v in request.query_params.items() if v is not None}
        return filtered or None


class NemoClient(BaseNemoClient):
    """Sync HTTP client for NeMo Platform APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        workspace: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(base_url=base_url, workspace=workspace)
        self._http = http_client or httpx.Client(
            headers=dict(default_headers) if default_headers else None,
            timeout=timeout,
        )

    @overload
    def send(
        self, request: PreparedRequest[BinaryContent], *, headers: dict[str, str] | None = None
    ) -> NemoBinaryResponse: ...
    @overload
    def send(
        self, request: PreparedRequest[Stream[ModelT]], *, headers: dict[str, str] | None = None
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def send(self, request: PreparedRequest[None], *, headers: dict[str, str] | None = None) -> NemoResponse[None]: ...
    @overload
    def send(
        self, request: PreparedRequest[ResponseT], *, headers: dict[str, str] | None = None
    ) -> NemoResponse[ResponseT]: ...

    def send(
        self, request: PreparedRequest, *, headers: dict[str, str] | None = None
    ) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        """Send a prepared request and return a typed response.

        Args:
            request: The prepared request to send.
            headers: Optional per-request headers merged on top of client
                defaults and content-type headers.

        For binary and streaming endpoints, the caller should use the
        response as a context manager to ensure the connection is closed::

            with client.send(endpoints.download(name="file.csv")) as resp:
                for chunk in resp:
                    f.write(chunk)
        """
        if headers:
            request = request.with_headers(headers)
        url = self._resolve_path(request)
        req_headers = self._request_headers(request)
        params = self._resolve_query_params(request)

        if self._is_binary(request):
            stream_ctx = self._http.stream(
                request.method, url, content=request.content, headers=req_headers, params=params
            )
            return NemoBinaryResponse(stream_ctx, request)

        if self._is_stream(request):
            assert request.response_type is not None
            stream_ctx = self._http.stream(
                request.method, url, content=request.content, headers=req_headers, params=params
            )
            model_type = _get_stream_model_type(request.response_type)
            return NemoStreamResponse(stream_ctx, model_type, request)

        raw = self._http.request(request.method, url, content=request.content, headers=req_headers, params=params)
        body = None
        if raw.is_success and request.response_type is not None:
            body = request.response_type.model_validate(raw.json())
        return NemoResponse(http_response=raw, body=body, request=request)


class AsyncNemoClient(BaseNemoClient):
    """Async HTTP client for NeMo Platform APIs.

    Async twin of :class:`NemoClient`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        workspace: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(base_url=base_url, workspace=workspace)
        self._http = http_client or httpx.AsyncClient(
            headers=dict(default_headers) if default_headers else None,
            timeout=timeout,
        )

    @overload
    async def send(
        self, request: PreparedRequest[BinaryContent], *, headers: dict[str, str] | None = None
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def send(
        self, request: PreparedRequest[Stream[ModelT]], *, headers: dict[str, str] | None = None
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def send(
        self, request: PreparedRequest[None], *, headers: dict[str, str] | None = None
    ) -> NemoResponse[None]: ...
    @overload
    async def send(
        self, request: PreparedRequest[ResponseT], *, headers: dict[str, str] | None = None
    ) -> NemoResponse[ResponseT]: ...

    async def send(
        self, request: PreparedRequest, *, headers: dict[str, str] | None = None
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        """Send a prepared request and return a typed response."""
        if headers:
            request = request.with_headers(headers)
        url = self._resolve_path(request)
        req_headers = self._request_headers(request)
        params = self._resolve_query_params(request)

        if self._is_binary(request):
            stream_ctx = self._http.stream(
                request.method, url, content=request.content, headers=req_headers, params=params
            )
            return AsyncNemoBinaryResponse(stream_ctx, request)

        if self._is_stream(request):
            assert request.response_type is not None
            stream_ctx = self._http.stream(
                request.method, url, content=request.content, headers=req_headers, params=params
            )
            model_type = _get_stream_model_type(request.response_type)
            return AsyncNemoStreamResponse(stream_ctx, model_type, request)

        raw = await self._http.request(request.method, url, content=request.content, headers=req_headers, params=params)
        body = None
        if raw.is_success and request.response_type is not None:
            body = request.response_type.model_validate(raw.json())
        return NemoResponse(http_response=raw, body=body, request=request)
