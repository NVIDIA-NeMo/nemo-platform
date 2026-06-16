# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP client for NeMo Platform.

Sends :class:`~.endpoint.PreparedRequest` objects and returns typed
:class:`~.response.NemoResponse` objects.  Subclass :class:`NemoClient`
and set ``api_prefix`` to scope requests to a specific API surface.

Usage::

    from nemo_platform_plugin.client import NemoClient

    class ExampleClient(NemoClient):
        api_prefix = "/apis/example"

    client = ExampleClient(base_url="http://localhost:8080")
    resp = client.send(CREATE_ITEM(CreateItemRequest(name="x"), workspace="default"))
    resp.body  # ItemResponse — fully typed
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

import httpx
from pydantic import BaseModel

from nemo_platform_plugin.client.endpoint import PreparedRequest
from nemo_platform_plugin.client.response import NemoResponse

ResponseT = TypeVar("ResponseT", bound=BaseModel)

DEFAULT_TIMEOUT = 60.0


class BaseNemoClient:
    """Shared logic for sync and async NeMo clients.

    Handles URL construction, request serialisation, and response parsing.
    Subclasses provide the actual HTTP transport (sync or async).

    Parameters
    ----------
    base_url:
        Base URL of the NeMo Platform instance
        (e.g. ``"http://localhost:8080"``).
    """

    api_prefix: str = ""

    def __init__(self, *, base_url: str, workspace: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._workspace = workspace

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def workspace(self) -> str | None:
        return self._workspace

    def _build_url(self, path: str) -> str:
        if self._workspace and "{workspace}" in path:
            path = path.replace("{workspace}", self._workspace)
        return self._base_url + self.api_prefix + path

    def _prepare_json(self, request: PreparedRequest[ResponseT]) -> dict | None:
        if request.body is not None:
            return request.body.model_dump(mode="json")
        return None

    def _parse_response(self, request: PreparedRequest[ResponseT], raw: httpx.Response) -> NemoResponse[ResponseT]:
        raw.raise_for_status()
        body = request.response_type.model_validate(raw.json()) if request.response_type is not None else None
        return NemoResponse(
            http_response=raw,
            body=body,  # type: ignore[arg-type]
        )


class NemoClient(BaseNemoClient):
    """Sync HTTP client for NeMo Platform APIs.

    Subclass and set ``api_prefix`` to the API mount point
    (e.g. ``"/apis/example"``).

    Parameters
    ----------
    base_url:
        Base URL of the NeMo Platform instance
        (e.g. ``"http://localhost:8080"``).
    workspace:
        Default workspace injected into ``{workspace}`` path parameters.
    default_headers:
        Additional HTTP headers sent with every request (e.g. auth tokens).
    timeout:
        Request timeout in seconds.  Defaults to 60.
    http_client:
        Optional pre-configured ``httpx.Client``.  When provided,
        ``default_headers`` and ``timeout`` are ignored.
    """

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

    def send(self, request: PreparedRequest[ResponseT]) -> NemoResponse[ResponseT]:
        """Send a prepared request and return a typed response.

        The return type is inferred from the endpoint definition — callers
        get ``NemoResponse[UserResponse]`` (or whatever ``R`` is) without
        any casts or annotations.
        """
        url = self._build_url(request.path)
        raw = self._http.request(
            request.method,
            url,
            json=self._prepare_json(request),
        )
        return self._parse_response(request, raw)


class AsyncNemoClient(BaseNemoClient):
    """Async HTTP client for NeMo Platform APIs.

    Async twin of :class:`NemoClient`.

    Parameters
    ----------
    base_url:
        Base URL of the NeMo Platform instance.
    workspace:
        Default workspace injected into ``{workspace}`` path parameters.
    default_headers:
        Additional HTTP headers sent with every request.
    timeout:
        Request timeout in seconds.  Defaults to 60.
    http_client:
        Optional pre-configured ``httpx.AsyncClient``.  When provided,
        ``default_headers`` and ``timeout`` are ignored.
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

    async def send(self, request: PreparedRequest[ResponseT]) -> NemoResponse[ResponseT]:
        """Send a prepared request and return a typed response."""
        url = self._build_url(request.path)
        raw = await self._http.request(
            request.method,
            url,
            json=self._prepare_json(request),
        )
        return self._parse_response(request, raw)
