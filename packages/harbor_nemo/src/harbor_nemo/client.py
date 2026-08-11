# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP transport and error translation for the NeMo registry backend.

Talks to the platform's documented REST API with ``httpx`` rather than importing the NeMo
Platform SDK. The SDK would drag the whole platform into any environment that installs
``harbor``, and a registry backend needs three endpoint families (filesets, tasks, tasksets),
not a platform client.

**Error translation is the point of this module.** A caller holds a ``BasePublisher`` and
cannot be expected to catch transport exceptions, so every response passes through
:meth:`NemoClient.request`, which maps status codes onto ``harbor.publisher.errors``. The one
rule that is load bearing: a 404 becomes :class:`NotFound`, which read paths convert to
``ValueError`` and *nothing else does*. ``BaseRegistryBackend.package_type`` distinguishes
"absent" from "broken" by catching exactly ``ValueError``, so translating an auth or transport
failure into a not-found signal would report "package not found" to a user whose real problem
is that they are logged out.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx
from harbor.publisher.errors import (
    PublishAuthError,
    PublishBackendError,
    PublishPermissionError,
)

from harbor_nemo.config import NemoConfig


class NotFound(Exception):
    """The platform returned 404.

    Not a ``ValueError`` itself: whether a miss means "no such package" (read paths, where
    ``ValueError`` is the contract) or a genuine backend failure (a publish whose fileset
    vanished mid-flight) depends on the caller, so the decision is left to them.
    """


def _detail(response: httpx.Response) -> str:
    """Pull the platform's own error text out of a response, falling back to the status line."""
    try:
        body = response.json()
    except Exception:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("message")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)
    return str(body)


class NemoClient:
    """A thin async HTTP client whose failures are already Harbor's error types."""

    def __init__(self, config: NemoConfig) -> None:
        self.config = config
        headers = {"Accept": "application/json"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        self._client = httpx.AsyncClient(headers=headers, timeout=config.timeout_sec)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        content: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Perform a request, translating every failure into a Harbor-visible error.

        Returns the raw response on success so callers can read the *status code* — the
        evaluator's ``PUT`` distinguishes 200 ("content already published, no new revision")
        from 201 ("new revision"), which is exactly Harbor's ``skipped`` signal and is
        available nowhere else in the response.
        """
        try:
            response = await self._client.request(
                method, url, json=json, content=content, params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, timeout. Emphatically *not* a not-found: a
            # platform that is down must not be reported as a package that does not exist.
            raise PublishBackendError(f"Could not reach the NeMo platform at {url}: {exc}") from exc

        if response.status_code == 401:
            raise PublishAuthError(
                "Not authenticated with the NeMo platform. Set NMP_TOKEN (or NMP_API_KEY) to a "
                f"valid token for {self.config.base_url}."
            )
        if response.status_code == 403:
            raise PublishPermissionError(
                f"You don't have permission to write to workspace "
                f"{self.config.workspace!r} on {self.config.base_url}."
            )
        if response.status_code == 404:
            raise NotFound(_detail(response))
        if response.status_code >= 400:
            raise PublishBackendError(_detail(response))
        return response

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        return (await self.request("GET", url, params=params)).json()
