# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoClient factory for task containers and services.

Analogous to :mod:`nemo_platform_plugin.sdk_provider` but returns
:class:`~nemo_platform_plugin.client.client.NemoClient` /
:class:`~nemo_platform_plugin.client.client.AsyncNemoClient` instead of
``NeMoPlatform`` / ``AsyncNeMoPlatform``.

Lookup order for the provider
-----------------------------

1. **Explicit override** — set via :func:`set_client_provider` (for tests).
2. **Entry-point discovery** — scans the ``nemo.client_provider`` group.
3. **Built-in default** — :class:`DefaultNemoClientProvider`, an env-var-based
   implementation that reads ``NMP_BASE_URL`` and ``NMP_PRINCIPAL``.
"""

from __future__ import annotations

import json
import logging
import os
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

logger = logging.getLogger(__name__)

_INTERNAL_REQUEST_HEADER = "X-NMP-Internal"
_NMP_PRINCIPAL_ENVVAR = "NMP_PRINCIPAL"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class NemoClientProvider(Protocol):
    """Contract for building authenticated NemoClient handles."""

    def get_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> NemoClient:
        """Build a sync NemoClient handle."""

    def get_async_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> AsyncNemoClient:
        """Build an async NemoClient handle."""


# ---------------------------------------------------------------------------
# Default provider (env-var based)
# ---------------------------------------------------------------------------


def _read_principal_from_env() -> dict[str, Any] | None:
    raw = os.environ.get(_NMP_PRINCIPAL_ENVVAR)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {_NMP_PRINCIPAL_ENVVAR}: {exc}") from exc
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return data


def _on_behalf_of_headers(principal: dict[str, Any]) -> dict[str, str]:
    if principal.get("on_behalf_of"):
        effective_id = principal["on_behalf_of"]
        effective_email = principal.get("on_behalf_of_email")
        effective_groups = principal.get("on_behalf_of_groups") or []
    else:
        effective_id = principal["id"]
        effective_email = principal.get("email")
        effective_groups = principal.get("groups") or []

    headers: dict[str, str] = {"X-NMP-Principal-On-Behalf-Of": effective_id}
    if effective_email:
        headers["X-NMP-Principal-On-Behalf-Of-Email"] = effective_email
    if effective_groups:
        headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(effective_groups)
    return headers


class DefaultNemoClientProvider:
    """Env-var-based provider that ships with the plugin package.

    Reads ``NMP_BASE_URL`` and ``NMP_PRINCIPAL``.
    """

    def get_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> NemoClient:
        headers = self._build_headers(as_service=as_service, internal=internal, on_behalf_of=on_behalf_of)
        return NemoClient(base_url=self._base_url(), default_headers=headers or None)

    def get_async_nemo_client(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> AsyncNemoClient:
        headers = self._build_headers(as_service=as_service, internal=internal, on_behalf_of=on_behalf_of)
        return AsyncNemoClient(base_url=self._base_url(), default_headers=headers or None)

    @staticmethod
    def _build_headers(
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}

        if internal:
            headers[_INTERNAL_REQUEST_HEADER] = "true"

        if as_service is not None:
            headers["X-NMP-Principal-Id"] = f"service:{as_service}"
        else:
            principal = _read_principal_from_env()
            if principal is not None:
                headers["X-NMP-Principal-Id"] = principal["id"]
                if principal.get("email"):
                    headers["X-NMP-Principal-Email"] = principal["email"]
                if principal.get("groups"):
                    headers["X-NMP-Principal-Groups"] = ",".join(principal["groups"])

        if on_behalf_of is not None:
            headers["X-NMP-Principal-On-Behalf-Of"] = on_behalf_of

        return headers

    @staticmethod
    def _base_url() -> str:
        return os.environ.get("NMP_BASE_URL", "http://localhost:8080")


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------

_cached_provider: NemoClientProvider | None = None


def set_client_provider(provider: NemoClientProvider | None) -> None:
    """Override the provider (primarily for tests).

    Pass ``None`` to clear the override and fall back to entry-point
    discovery on the next call.
    """
    global _cached_provider
    _cached_provider = provider


def _resolve_provider() -> NemoClientProvider:
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    eps = {ep.name: ep for ep in entry_points(group="nemo.client_provider")}
    if len(eps) > 1:
        names = ", ".join(eps)
        raise RuntimeError(
            f"Multiple NemoClient providers registered under 'nemo.client_provider': {names}. "
            "Only one provider should be registered."
        )
    for ep in eps.values():
        try:
            obj = ep.load()
            if isinstance(obj, type):
                obj = obj()
            if isinstance(obj, NemoClientProvider):
                logger.debug("Using NemoClient provider from entry-point %r", ep.name)
                _cached_provider = obj
                return obj
        except Exception:
            logger.warning("Failed to load NemoClient provider %r; skipping", ep.name, exc_info=True)

    logger.debug("No entry-point NemoClient provider found; using DefaultNemoClientProvider")
    _cached_provider = DefaultNemoClientProvider()
    return _cached_provider


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_nemo_client(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> NemoClient:
    """Build a sync NemoClient for the current service context."""
    return _resolve_provider().get_nemo_client(
        as_service=as_service,
        internal=internal,
        on_behalf_of=on_behalf_of,
    )


def get_async_nemo_client(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> AsyncNemoClient:
    """Build an async NemoClient for the current service context."""
    return _resolve_provider().get_async_nemo_client(
        as_service=as_service,
        internal=internal,
        on_behalf_of=on_behalf_of,
    )
