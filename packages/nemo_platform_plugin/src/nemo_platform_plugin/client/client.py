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
import copy
import inspect
import json
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from functools import cache
from pathlib import Path
from typing import Any, Self, TypeVar, cast, get_args, get_origin, overload
from urllib.parse import quote

import httpx
from nemo_platform_plugin.client.auth import (
    StaticToken,
    TokenProvider,
)
from nemo_platform_plugin.client.errors import (
    NemoResponseValidationError,
    NemoTransportError,
    raise_for_status,
)
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
    StrategyT,
    Stream,
)
from pydantic import BaseModel, TypeAdapter, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

DEFAULT_TIMEOUT = 60.0


@cache
def _type_adapter(response_type: type[ResponseT]) -> TypeAdapter[ResponseT]:
    """Build each response annotation's validation schema once."""
    return TypeAdapter(response_type)


def _parse_json_body(response_type: type[ResponseT], data: object) -> ResponseT:
    """Parse a decoded JSON body against an endpoint's return annotation.

    ``TypeAdapter`` handles both model classes and arbitrary annotations such as
    ``list[Profile]`` while preserving the annotation's type for callers.
    """
    return _type_adapter(response_type).validate_python(data)


def _parse_response_body(response_type: type[ResponseT], response: httpx.Response) -> ResponseT:
    """Decode and validate a response, normalizing contract failures."""
    try:
        return _parse_json_body(response_type, response.json())
    except (ValueError, ValidationError) as exc:
        raise NemoResponseValidationError(response, exc) from exc


def _get_stream_model_type(response_type: type[Stream[ModelT]]) -> type[ModelT]:
    """Extract the ModelT from a Stream[ModelT] generic alias."""
    args = get_args(response_type)
    if not args:
        raise TypeError(f"Stream response type must be parameterized, got {response_type}")
    return cast(type[ModelT], args[0])


def _get_paginated_types(
    response_type: type[Paginated[ModelT, StrategyT]],
) -> tuple[type[ModelT], type[StrategyT]]:
    """Extract (ModelT, StrategyT) from a Paginated[ModelT, StrategyT] generic alias."""
    args = get_args(response_type)
    if not args:
        raise TypeError(f"Paginated response type must be parameterized, got {response_type}")
    model_type = args[0]
    strategy_type = args[1] if len(args) > 1 else OffsetPagination
    return cast(type[ModelT], model_type), cast(type[StrategyT], strategy_type)


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


def _should_resolve_conflict(response: httpx.Response, request: PreparedRequest) -> bool:
    """Whether a 409 should be resolved by replaying the linked retrieve request.

    True when the create was sent with ``exist_ok=True``, the server responded
    409 Conflict, and the endpoint declared a ``get_on_conflict`` resolver (whose
    prebuilt GET is on ``request.on_conflict_get``). In that case ``send()``
    replays that GET and returns the existing entity instead of raising.
    """
    if response.status_code != 409:
        return False
    if not (request.client_options or {}).get("exist_ok"):
        return False
    if request.on_conflict_get is None:
        raise ValueError(
            "exist_ok=True was set on a create request whose endpoint declares no "
            "get_on_conflict resolver, so the existing entity cannot be retrieved "
            "on conflict. Add get_on_conflict=<resolver> to the @post endpoint."
        )
    return True


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
        auth: TokenProvider | str | None = None,
        retry: RetryPolicy | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._workspace = workspace
        self._auth: TokenProvider | None = StaticToken(auth) if isinstance(auth, str) else auth
        self._retry = retry
        self._default_headers = dict(default_headers) if default_headers else {}
        self._timeout: float | httpx.Timeout | None = None

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
        encoded_params = {name: quote(str(value), safe="") for name, value in params.items()}
        try:
            path = request.path_template.format_map(encoded_params)
        except KeyError as exc:
            raise ValueError(f"Missing path parameter {exc} for {request.method} {request.path_template}") from exc
        return self._base_url + path

    def _request_headers(self, request: PreparedRequest) -> dict[str, str] | None:
        headers: dict[str, str] = {}
        if self._default_headers:
            headers.update(self._default_headers)
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

    def with_options(
        self,
        *,
        headers: Mapping[str, str] | None = None,
        retry: RetryPolicy | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> Self:
        """Return a copy of this client with the given options merged in.

        The returned client shares the underlying HTTP transport, so it is
        cheap to create.  Useful for one-off header, retry, or timeout
        overrides when calling ``method()``-bound endpoints::

            client.with_headers({"Range": "bytes=0-99"}).download_file(...)
            client.with_options(timeout=300).update_fileset(...)
        """
        clone = copy.copy(self)
        if headers:
            clone._default_headers = {**self._default_headers, **headers}
        if retry is not None:
            clone._retry = retry
        if timeout is not None:
            clone._timeout = timeout
        return clone

    def with_headers(self, headers: Mapping[str, str]) -> Self:
        """Shorthand for ``with_options(headers=...)``."""
        return self.with_options(headers=headers)

    def with_retry(self, retry: RetryPolicy) -> Self:
        """Shorthand for ``with_options(retry=...)``."""
        return self.with_options(retry=retry)

    def _resolve_query_params(self, request: PreparedRequest) -> dict[str, str | int | bool] | None:
        """Filter out None values and JSON-serialize dicts/lists in query params."""
        if request.query_params is None:
            return None
        filtered = {}
        for k, v in request.query_params.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                filtered[k] = json.dumps(v)
            else:
                filtered[k] = v
        return filtered or None


class NemoClient(BaseNemoClient):
    """Sync HTTP client for NeMo Platform APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        workspace: str | None = None,
        auth: TokenProvider | str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry: RetryPolicy | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url, workspace=workspace, auth=auth, retry=retry, default_headers=default_headers
        )
        self._http = http_client or httpx.Client(
            headers=dict(default_headers) if default_headers else None,
            timeout=timeout,
        )

    @classmethod
    def from_client(cls, client: NemoClient) -> Self:
        """Create an instance of this subclass sharing the transport of *client*."""
        return cls(
            base_url=client.base_url,
            workspace=client.workspace,
            auth=client._auth,
            default_headers=client._default_headers or None,
            retry=client._retry,
            http_client=client._http,
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
        request: PreparedRequest[Paginated[ModelT, StrategyT]],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> NemoPaginatedResponse[ModelT, StrategyT]: ...
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

    @classmethod
    def from_config(
        cls,
        context: str | None = None,
        config_path: Path | str | None = None,
    ) -> NemoClient:
        """Create a NemoClient from the user's nmp config file.

        Args:
            context: Context name to use (default: active context).
            config_path: Path to config file (default: ``~/.config/nmp/config.yaml``).
        """
        return _client_from_config(cls, context=context, config_path=config_path)

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

        # Inject auth header if a TokenProvider is configured.
        # NOTE: If a 401 occurs despite this, a future enhancement could
        # call provider.force_refresh() and retry once. The proactive
        # refresh margin (60s) makes this unlikely in practice.
        if self._auth:
            token = self._auth.get_access_token()
            request = request.with_headers({"Authorization": f"Bearer {token}"})

        url = self._resolve_path(request)
        req_headers = self._request_headers(request)
        params = self._resolve_query_params(request)
        resolved_retry = self._resolve_retry(retry)

        if self._is_binary(request):
            stream_ctx = self._stream_with_retry(request, url, req_headers, params, resolved_retry)
            return NemoBinaryResponse(stream_ctx, request)

        if self._is_stream(request):
            assert request.response_type is not None
            stream_ctx = self._stream_with_retry(request, url, req_headers, params, resolved_retry)
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
        if _should_resolve_conflict(raw, request):
            assert request.on_conflict_get is not None
            return self.send(request.on_conflict_get, headers=headers, retry=retry)
        raise_for_status(raw)
        body = None
        if request.response_type is not None:
            body = _parse_response_body(request.response_type, raw)
        return NemoResponse(http_response=raw, body=body, request=request)

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
                kwargs: dict = {"content": request.content, "headers": headers, "params": params}
                if self._timeout is not None:
                    kwargs["timeout"] = self._timeout
                raw = self._http.request(request.method, url, **kwargs)
            except httpx.TransportError as exc:
                backoff = _should_retry(None, exc, attempt, retry) if retry else None
                if backoff is not None:
                    time.sleep(backoff)
                    continue
                raise NemoTransportError(exc) from exc
            if retry:
                backoff = _should_retry(raw, None, attempt, retry)
                if backoff is not None:
                    last_response = raw
                    time.sleep(backoff)
                    continue
            return raw

        assert last_response is not None
        return last_response

    @contextmanager
    def _stream_with_retry(
        self,
        request: PreparedRequest,
        url: str,
        headers: dict[str, str] | None,
        params: dict | None,
        retry: RetryPolicy | None,
    ) -> Iterator[httpx.Response]:
        """Open a stream, retrying failures before handing it to the caller."""
        for attempt in range(retry.max_retries + 1 if retry else 1):
            yielded = False
            try:
                kwargs: dict = {"content": request.content, "headers": headers, "params": params}
                if self._timeout is not None:
                    kwargs["timeout"] = self._timeout
                with self._http.stream(request.method, url, **kwargs) as raw:
                    backoff = _should_retry(raw, None, attempt, retry) if retry else None
                    if backoff is not None:
                        time.sleep(backoff)
                        continue
                    yielded = True
                    yield raw
                    return
            except httpx.TransportError as exc:
                if yielded:
                    raise NemoTransportError(exc) from exc
                backoff = _should_retry(None, exc, attempt, retry) if retry else None
                if backoff is not None:
                    time.sleep(backoff)
                    continue
                raise NemoTransportError(exc) from exc

    def _make_page_fetcher(
        self, strategy: type[PaginationStrategy[Any, Any]], retry: RetryPolicy | None = None
    ) -> SyncPageFetcher:
        """Create a page-fetching callback bound to this client and strategy."""

        def fetch(request: PreparedRequest, page: Any) -> httpx.Response:
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
        auth: TokenProvider | str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry: RetryPolicy | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url, workspace=workspace, auth=auth, retry=retry, default_headers=default_headers
        )
        self._http = http_client or httpx.AsyncClient(
            headers=dict(default_headers) if default_headers else None,
            timeout=timeout,
        )

    @classmethod
    def from_client(cls, client: AsyncNemoClient) -> Self:
        """Create an instance of this subclass sharing the transport of *client*."""
        return cls(
            base_url=client.base_url,
            workspace=client.workspace,
            auth=client._auth,
            default_headers=client._default_headers or None,
            retry=client._retry,
            http_client=client._http,
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
        request: PreparedRequest[Paginated[ModelT, StrategyT]],
        *,
        headers: dict[str, str] | None = None,
        retry: RetryPolicy | None = None,
    ) -> AsyncNemoPaginatedResponse[ModelT, StrategyT]: ...
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

    @classmethod
    def from_config(
        cls,
        context: str | None = None,
        config_path: Path | str | None = None,
    ) -> AsyncNemoClient:
        """Create an AsyncNemoClient from the user's nmp config file.

        Args:
            context: Context name to use (default: active context).
            config_path: Path to config file (default: ``~/.config/nmp/config.yaml``).
        """
        return _client_from_config(cls, context=context, config_path=config_path)

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

        # Inject auth header. Three cases, in priority order:
        # 1. Provider has get_access_token_async() (e.g. OIDCTokenProvider) — use it.
        # 2. Provider.get_access_token() is a coroutine function — await it.
        # 3. Provider.get_access_token() is sync — run in a thread to avoid
        #    blocking the event loop during IO (e.g. token refresh HTTP calls).
        if self._auth:
            get_async = getattr(self._auth, "get_access_token_async", None)
            if get_async is not None and callable(get_async):
                token = await get_async()
            elif inspect.iscoroutinefunction(self._auth.get_access_token):
                token = await self._auth.get_access_token()
            else:
                token = await asyncio.to_thread(self._auth.get_access_token)
            request = request.with_headers({"Authorization": f"Bearer {token}"})

        url = self._resolve_path(request)
        req_headers = self._request_headers(request)
        params = self._resolve_query_params(request)
        resolved_retry = self._resolve_retry(retry)

        if self._is_binary(request):
            stream_ctx = self._stream_with_retry(request, url, req_headers, params, resolved_retry)
            return AsyncNemoBinaryResponse(stream_ctx, request)

        if self._is_stream(request):
            assert request.response_type is not None
            stream_ctx = self._stream_with_retry(request, url, req_headers, params, resolved_retry)
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
        if _should_resolve_conflict(raw, request):
            assert request.on_conflict_get is not None
            return await self.send(request.on_conflict_get, headers=headers, retry=retry)
        raise_for_status(raw)
        body = None
        if request.response_type is not None:
            body = _parse_response_body(request.response_type, raw)
        return NemoResponse(http_response=raw, body=body, request=request)

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
                kwargs: dict = {"content": request.content, "headers": headers, "params": params}
                if self._timeout is not None:
                    kwargs["timeout"] = self._timeout
                raw = await self._http.request(request.method, url, **kwargs)
            except httpx.TransportError as exc:
                backoff = _should_retry(None, exc, attempt, retry) if retry else None
                if backoff is not None:
                    await asyncio.sleep(backoff)
                    continue
                raise NemoTransportError(exc) from exc
            if retry:
                backoff = _should_retry(raw, None, attempt, retry)
                if backoff is not None:
                    last_response = raw
                    await asyncio.sleep(backoff)
                    continue
            return raw

        assert last_response is not None
        return last_response

    @asynccontextmanager
    async def _stream_with_retry(
        self,
        request: PreparedRequest,
        url: str,
        headers: dict[str, str] | None,
        params: dict | None,
        retry: RetryPolicy | None,
    ) -> AsyncIterator[httpx.Response]:
        """Open an async stream, retrying failures before handing it to the caller."""
        for attempt in range(retry.max_retries + 1 if retry else 1):
            yielded = False
            try:
                kwargs: dict = {"content": request.content, "headers": headers, "params": params}
                if self._timeout is not None:
                    kwargs["timeout"] = self._timeout
                async with self._http.stream(request.method, url, **kwargs) as raw:
                    backoff = _should_retry(raw, None, attempt, retry) if retry else None
                    if backoff is not None:
                        await asyncio.sleep(backoff)
                        continue
                    yielded = True
                    yield raw
                    return
            except httpx.TransportError as exc:
                if yielded:
                    raise NemoTransportError(exc) from exc
                backoff = _should_retry(None, exc, attempt, retry) if retry else None
                if backoff is not None:
                    await asyncio.sleep(backoff)
                    continue
                raise NemoTransportError(exc) from exc

    def _make_page_fetcher(
        self, strategy: type[PaginationStrategy[Any, Any]], retry: RetryPolicy | None = None
    ) -> AsyncPageFetcher:
        """Create an async page-fetching callback bound to this client and strategy."""

        async def fetch(request: PreparedRequest, page: Any) -> httpx.Response:
            url = self._resolve_path(request)
            req_headers = self._request_headers(request)
            existing_params = self._resolve_query_params(request) or {}
            page_params = strategy.page_query_params(page)
            params = {**existing_params, **page_params}
            return await self._request_with_retry(request, url, req_headers, params, retry)

        return fetch


# ---------------------------------------------------------------------------
# from_config helper (shared by NemoClient and AsyncNemoClient)
# ---------------------------------------------------------------------------

_ClientT = TypeVar("_ClientT", NemoClient, AsyncNemoClient)


def _client_from_config(
    cls: type[_ClientT],
    *,
    context: str | None = None,
    config_path: Path | str | None = None,
) -> _ClientT:
    """Shared implementation for NemoClient.from_config / AsyncNemoClient.from_config."""
    from nemo_platform_plugin.client.config.config import Config
    from nemo_platform_plugin.client.config.models import ConfigParams, OAuthUser
    from nemo_platform_plugin.client.oidc_factory import resolve_oidc_provider

    resolved_path = Path(config_path) if isinstance(config_path, str) else config_path
    overrides: ConfigParams | None = None
    if context is not None:
        overrides = {"current_context": context}
    config = Config.load(config_path=resolved_path, overrides=overrides)
    actual_config_path = config.get_config_path() or Config.get_default_config_path()
    config_exists = actual_config_path.exists()
    # If the token came from NMP_ACCESS_TOKEN (env override), it's not from
    # the config file — don't cache or persist provider state for it.
    explicit_access_token = config.access_token is not None
    ctx = config.resolve()

    auth: TokenProvider | str | None = None

    if isinstance(ctx.user, OAuthUser):
        auth = resolve_oidc_provider(
            base_url=str(ctx.cluster.base_url),
            context_name=ctx.context_name,
            access_token=ctx.user.token.get_secret_value(),
            refresh_token=ctx.user.refresh_token.get_secret_value() if ctx.user.refresh_token else None,
            config_exists=config_exists,
            config_path=actual_config_path,
            explicit_access_token=explicit_access_token,
        )
    elif ctx.user:
        client_config = ctx.user.get_client_config()
        raw_headers = client_config.get("default_headers")
        if isinstance(raw_headers, dict):
            raw_auth = dict(raw_headers).get("Authorization")
            if isinstance(raw_auth, str) and raw_auth.startswith("Bearer "):
                auth = raw_auth.removeprefix("Bearer ")

    return cls(base_url=str(ctx.cluster.base_url), workspace=ctx.workspace, auth=auth)
