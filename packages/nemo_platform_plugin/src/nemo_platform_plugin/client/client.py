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
- ``Paginated[T]`` → :class:`~.response.NemoPaginatedResponse[T]`
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any, TypeVar, get_args, get_origin, overload

import httpx
from nemo_platform_plugin.client.response import (
    AsyncNemoBinaryResponse,
    AsyncNemoPaginatedResponse,
    AsyncNemoStreamResponse,
    AsyncPageFetcher,
    NemoBinaryResponse,
    NemoPaginatedResponse,
    NemoResponse,
    NemoStreamResponse,
    SyncPageFetcher,
)
from nemo_platform_plugin.client.types import (
    BinaryContent,
    OffsetPagination,
    Paginated,
    PaginationStrategy,
    PreparedRequest,
    ResponseT,
    RetryPolicy,
    Stream,
)
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_TIMEOUT = 60.0


def _get_stream_model_type(response_type: type) -> type[BaseModel]:
    """Extract the ModelT from a Stream[ModelT] generic alias."""
    args = get_args(response_type)
    if not args:
        raise TypeError(f"Stream response type must be parameterized, got {response_type}")
    return args[0]


def _get_paginated_types(response_type: type) -> tuple[type[BaseModel], type]:
    """Extract (ModelT, StrategyT) from a Paginated[ModelT, StrategyT] generic alias."""
    args = get_args(response_type)
    if not args:
        raise TypeError(f"Paginated response type must be parameterized, got {response_type}")
    model_type = args[0]
    strategy_type = args[1] if len(args) > 1 else OffsetPagination
    return model_type, strategy_type


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


def _should_retry(
    response: httpx.Response | None,
    exc: httpx.TransportError | None,
    attempt: int,
    policy: RetryPolicy,
) -> float | None:
    """Decide whether to retry and return the backoff duration, or None to stop.

    Shared decision logic used by both sync and async retry paths.
    Returns the sleep duration if a retry should happen, or ``None`` if
    the response should be returned / the exception re-raised.
    """
    is_last = attempt >= policy.max_retries
    if is_last:
        return None
    if exc is not None:
        return policy.backoff_base * (2**attempt)
    if response is not None and response.status_code in policy.retryable_status_codes:
        return policy.backoff_base * (2**attempt)
    return None


class BaseNemoClient:
    """Shared logic for sync and async NeMo clients.

    Handles URL construction and request serialisation.
    Subclasses provide the actual HTTP transport (sync or async).
    """

    def __init__(
        self,
        *,
        base_url: str,
        workspace: str | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._workspace = workspace
        self._retry = retry

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def workspace(self) -> str | None:
        return self._workspace

    @property
    def retry(self) -> RetryPolicy | None:
        return self._retry

    def _resolve_retry(self, retry: RetryPolicy | None) -> RetryPolicy | None:
        """Resolve retry policy: per-call override > client default."""
        if retry is not None:
            return retry
        return self._retry

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

    def _is_paginated(self, request: PreparedRequest) -> bool:
        return get_origin(request.response_type) is Paginated

    def _resolve_query_params(self, request: PreparedRequest) -> dict[str, str | int | bool] | None:
        """Filter out None values from query params for httpx."""
        if request.query_params is None:
            return None
        filtered = {k: v for k, v in request.query_params.items() if v is not None}
        return filtered or None

    def _apply_client_options(self, request: PreparedRequest, response: NemoResponse) -> NemoResponse:
        """Apply blessed client options (e.g. ``exist_ok``) to the response.

        Options are stashed on ``PreparedRequest.client_options`` by the
        endpoint decorator and applied here after the HTTP call completes.
        """
        if not request.client_options:
            return response

        if request.client_options.get("exist_ok"):
            if response.http_response.status_code == 409:
                body = response.body
                if body is None and request.response_type is not None:
                    try:
                        body = request.response_type.model_validate(response.http_response.json())
                    except (ValueError, TypeError):
                        pass
                return NemoResponse(http_response=response.http_response, body=body, request=request)

        return response


class NemoClient(BaseNemoClient):
    """Sync HTTP client for NeMo Platform APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        workspace: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry: RetryPolicy | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(base_url=base_url, workspace=workspace, retry=retry)
        self._http = http_client or httpx.Client(
            headers=dict(default_headers) if default_headers else None,
            timeout=timeout,
        )

    @overload
    def send(
        self,
        request: PreparedRequest[BinaryContent],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoBinaryResponse: ...
    @overload
    def send(
        self,
        request: PreparedRequest[Stream[ModelT]],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def send(
        self,
        request: PreparedRequest[Paginated[ModelT, Any]],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoPaginatedResponse[ModelT]: ...
    @overload
    def send(
        self,
        request: PreparedRequest[None],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoResponse[None]: ...
    @overload
    def send(
        self,
        request: PreparedRequest[ResponseT],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoResponse[ResponseT]: ...

    def send(
        self,
        request: PreparedRequest,
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse | NemoPaginatedResponse:
        """Send a prepared request and return a typed response.

        Args:
            request: The prepared request to send.
            headers: Optional per-request headers merged on top of client
                defaults and content-type headers.
            retry: Optional per-request retry policy override. Takes
                precedence over client-level defaults.

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
        resolved_retry = self._resolve_retry(retry)

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

        if self._is_paginated(request):
            assert request.response_type is not None
            raw = self._request_with_retry(request, url, req_headers, params, resolved_retry)
            model_type, strategy = _get_paginated_types(request.response_type)
            return NemoPaginatedResponse(
                raw, model_type, request, self._make_page_fetcher(strategy, resolved_retry), strategy
            )

        raw = self._request_with_retry(request, url, req_headers, params, resolved_retry)
        body = None
        if raw.is_success and request.response_type is not None:
            body = request.response_type.model_validate(raw.json())
        response = NemoResponse(http_response=raw, body=body, request=request)
        return self._apply_client_options(request, response)

    def _request_with_retry(
        self,
        request: PreparedRequest,
        url: str,
        headers: dict[str, str] | None,
        params: dict | None,
        retry: RetryPolicy | None,
    ) -> httpx.Response:
        """Execute a single HTTP request with optional retry."""
        last_response: httpx.Response | None = None
        for attempt in range(retry.max_retries + 1 if retry else 1):
            try:
                raw = self._http.request(request.method, url, content=request.content, headers=headers, params=params)
            except httpx.TransportError as exc:
                backoff = _should_retry(None, exc, attempt, retry) if retry else None
                if backoff is not None:
                    time.sleep(backoff)
                    continue
                raise
            if retry:
                backoff = _should_retry(raw, None, attempt, retry)
                if backoff is not None:
                    last_response = raw
                    time.sleep(backoff)
                    continue
            return raw

        assert last_response is not None
        return last_response

    def _make_page_fetcher(
        self, strategy: type[PaginationStrategy], retry: RetryPolicy | None = None
    ) -> SyncPageFetcher:
        """Create a page-fetching callback bound to this client and strategy."""

        def fetch(request: PreparedRequest, page: int | str) -> httpx.Response:
            url = self._resolve_path(request)
            req_headers = self._request_headers(request)
            existing_params = self._resolve_query_params(request) or {}
            page_params = strategy.page_query_params(page)
            params = {**existing_params, **page_params}
            return self._request_with_retry(request, url, req_headers, params, retry)

        return fetch


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
        retry: RetryPolicy | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(base_url=base_url, workspace=workspace, retry=retry)
        self._http = http_client or httpx.AsyncClient(
            headers=dict(default_headers) if default_headers else None,
            timeout=timeout,
        )

    @overload
    async def send(
        self,
        request: PreparedRequest[BinaryContent],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def send(
        self,
        request: PreparedRequest[Stream[ModelT]],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def send(
        self,
        request: PreparedRequest[Paginated[ModelT, Any]],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> AsyncNemoPaginatedResponse[ModelT]: ...
    @overload
    async def send(
        self,
        request: PreparedRequest[None],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoResponse[None]: ...
    @overload
    async def send(
        self,
        request: PreparedRequest[ResponseT],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoResponse[ResponseT]: ...

    async def send(
        self,
        request: PreparedRequest,
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse | AsyncNemoPaginatedResponse:
        """Send a prepared request and return a typed response."""
        if headers:
            request = request.with_headers(headers)

        url = self._resolve_path(request)
        req_headers = self._request_headers(request)
        params = self._resolve_query_params(request)
        resolved_retry = self._resolve_retry(retry)

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

        if self._is_paginated(request):
            assert request.response_type is not None
            raw = await self._request_with_retry(request, url, req_headers, params, resolved_retry)
            model_type, strategy = _get_paginated_types(request.response_type)
            return AsyncNemoPaginatedResponse(
                raw, model_type, request, self._make_page_fetcher(strategy, resolved_retry), strategy
            )

        raw = await self._request_with_retry(request, url, req_headers, params, resolved_retry)
        body = None
        if raw.is_success and request.response_type is not None:
            body = request.response_type.model_validate(raw.json())
        response = NemoResponse(http_response=raw, body=body, request=request)
        return self._apply_client_options(request, response)

    async def _request_with_retry(
        self,
        request: PreparedRequest,
        url: str,
        headers: dict[str, str] | None,
        params: dict | None,
        retry: RetryPolicy | None,
    ) -> httpx.Response:
        """Execute a single async HTTP request with optional retry."""
        last_response: httpx.Response | None = None
        for attempt in range(retry.max_retries + 1 if retry else 1):
            try:
                raw = await self._http.request(
                    request.method, url, content=request.content, headers=headers, params=params
                )
            except httpx.TransportError as exc:
                backoff = _should_retry(None, exc, attempt, retry) if retry else None
                if backoff is not None:
                    await asyncio.sleep(backoff)
                    continue
                raise
            if retry:
                backoff = _should_retry(raw, None, attempt, retry)
                if backoff is not None:
                    last_response = raw
                    await asyncio.sleep(backoff)
                    continue
            return raw

        assert last_response is not None
        return last_response

    def _make_page_fetcher(
        self, strategy: type[PaginationStrategy], retry: RetryPolicy | None = None
    ) -> AsyncPageFetcher:
        """Create an async page-fetching callback bound to this client and strategy."""

        async def fetch(request: PreparedRequest, page: int | str) -> httpx.Response:
            url = self._resolve_path(request)
            req_headers = self._request_headers(request)
            existing_params = self._resolve_query_params(request) or {}
            page_params = strategy.page_query_params(page)
            params = {**existing_params, **page_params}
            return await self._request_with_retry(request, url, req_headers, params, retry)

        return fetch
