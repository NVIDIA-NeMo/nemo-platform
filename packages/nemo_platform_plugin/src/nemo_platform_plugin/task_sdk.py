# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK factory for task containers — the plugin-side interface for getting
authenticated :class:`~nemo_platform.NeMoPlatform` handles.

Plugin authors use :func:`get_task_sdk` in their ``__main__.py`` entrypoints
instead of importing from ``nmp.common.sdk_factory``.  This keeps the
``nemo-platform-plugin`` package free of ``nmp-common`` dependencies while
still allowing the platform to register a richer provider (with URL routing,
shared HTTP clients, OTEL headers, etc.) when ``nmp-common`` is installed.

Lookup order for the provider
-----------------------------

1. **Explicit override** — set via :func:`set_task_sdk_provider` (for tests).
2. **Entry-point discovery** — scans the ``nemo.task_sdk_provider`` group.
   When ``nmp-common`` is installed in the image (platform deployment), its
   provider is picked up automatically.
3. **Built-in default** — :class:`DefaultTaskSDKProvider`, an env-var-based
   implementation that reads ``NMP_BASE_URL`` and ``NMP_PRINCIPAL``.  Works
   for local development and gateway-routed task containers.

Usage from a plugin ``__main__.py``::

    from nemo_platform_plugin.task_sdk import get_task_sdk
    from nemo_platform_plugin.tasks.dispatcher import run_task

    sdk = get_task_sdk("evaluator")
    sys.exit(run_task(EvaluateJob, sdk=sdk))
"""

from __future__ import annotations

import json
import logging
import os
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

logger = logging.getLogger(__name__)

# Header name the platform uses to mark internal (service-to-service) requests.
_INTERNAL_REQUEST_HEADER = "X-NMP-Internal"

# Environment variable the jobs backend writes with the job creator's
# principal (JSON-serialised).
_NMP_PRINCIPAL_ENVVAR = "NMP_PRINCIPAL"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskSDKProvider(Protocol):
    """Contract for building authenticated SDK handles.

    Implementations live outside this module — the default is below;
    ``nmp-common`` ships a richer one registered via entry-point.
    """

    def get_task_sdk(self, service_name: str) -> NeMoPlatform:
        """Build an SDK for use inside a platform-spawned task container.

        The returned client authenticates as ``service:{service_name}`` and,
        when ``NMP_PRINCIPAL`` is set, acts on behalf of the job creator.
        """
        ...

    def get_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> NeMoPlatform:
        """Build a general-purpose sync SDK handle.

        Lower-level than :meth:`get_task_sdk` — callers choose their own
        auth mode.
        """
        ...

    def get_async_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> AsyncNeMoPlatform:
        """Build a general-purpose async SDK handle.

        Used by middleware and controllers that run inside the platform
        service process.
        """
        ...

    ...


# ---------------------------------------------------------------------------
# Default provider (env-var based, zero nmp-common dependency)
# ---------------------------------------------------------------------------


def _read_principal_from_env() -> dict[str, Any] | None:
    """Read and parse ``NMP_PRINCIPAL`` from the environment.

    Returns ``None`` when the variable is absent or empty.  Raises
    :class:`ValueError` on malformed JSON (matches ``nmp.common``
    behaviour so task containers surface the same error).
    """
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
    """Derive ``X-NMP-Principal-On-Behalf-Of*`` headers from a principal dict.

    Mirrors the header logic in ``nmp.common.sdk_factory._get_default_headers``
    so the default provider is wire-compatible.
    """
    # When the principal has an on_behalf_of field, use the effective principal
    # (the on-behalf-of identity).  Otherwise, use the principal itself.
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


class DefaultTaskSDKProvider:
    """Env-var-based provider that ships with the plugin package.

    Reads ``NMP_BASE_URL`` (default ``http://localhost:8080``) and
    ``NMP_PRINCIPAL`` — both are set by the jobs backend before launching
    task containers.  No ``nmp-common`` imports.
    """

    def get_task_sdk(self, service_name: str) -> NeMoPlatform:
        headers: dict[str, str] = {
            "X-NMP-Principal-Id": f"service:{service_name}",
            _INTERNAL_REQUEST_HEADER: "true",
        }

        principal = _read_principal_from_env()
        if principal is not None:
            headers.update(_on_behalf_of_headers(principal))
        else:
            logger.warning(
                "%s not set; task SDK will authenticate as service:%s without on-behalf-of delegation",
                _NMP_PRINCIPAL_ENVVAR,
                service_name,
            )

        return NeMoPlatform(
            base_url=self._base_url(),
            default_headers=headers,
        )

    def get_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> NeMoPlatform:
        headers = self._build_headers(as_service=as_service, internal=internal, on_behalf_of=on_behalf_of)
        return NeMoPlatform(
            base_url=self._base_url(),
            default_headers=headers if headers else None,
        )

    def get_async_platform_sdk(
        self,
        *,
        as_service: str | None = None,
        internal: bool = False,
        on_behalf_of: str | None = None,
    ) -> AsyncNeMoPlatform:
        headers = self._build_headers(as_service=as_service, internal=internal, on_behalf_of=on_behalf_of)
        return AsyncNeMoPlatform(
            base_url=self._base_url(),
            default_headers=headers if headers else None,
        )

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

_provider: TaskSDKProvider | None = None
_provider_resolved: bool = False


def set_task_sdk_provider(provider: TaskSDKProvider | None) -> None:
    """Override the provider (primarily for tests).

    Pass ``None`` to clear the override and fall back to entry-point
    discovery on the next call.
    """
    global _provider, _provider_resolved
    _provider = provider
    _provider_resolved = provider is not None


def _resolve_provider() -> TaskSDKProvider:
    """Resolve the provider once: entry-point → default."""
    global _provider, _provider_resolved

    if _provider_resolved:
        assert _provider is not None
        return _provider

    # Scan entry-points.
    eps = entry_points(group="nemo.task_sdk_provider")
    for ep in eps:
        try:
            factory = ep.load()
            loaded = factory() if callable(factory) and not isinstance(factory, type) else factory
            if isinstance(loaded, type):
                loaded = loaded()
            if isinstance(loaded, TaskSDKProvider):
                logger.debug("Using task SDK provider from entry-point %r", ep.name)
                _provider = loaded
                _provider_resolved = True
                return loaded
        except Exception:
            logger.warning("Failed to load task SDK provider %r; skipping", ep.name, exc_info=True)

    # Fall back to the built-in default.
    logger.debug("No entry-point task SDK provider found; using DefaultTaskSDKProvider")
    default = DefaultTaskSDKProvider()
    _provider = default
    _provider_resolved = True
    return default


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_task_sdk(service_name: str) -> NeMoPlatform:
    """Build an authenticated SDK for use inside a platform task container.

    Equivalent to the legacy ``nmp.common.sdk_factory.get_task_sdk`` but
    without requiring ``nmp-common`` as a dependency.

    Args:
        service_name: Plugin/service name used as the service principal
            (e.g. ``"evaluator"``).

    Returns:
        A :class:`~nemo_platform.NeMoPlatform` handle with internal +
        on-behalf-of headers set.
    """
    return _resolve_provider().get_task_sdk(service_name)


def get_platform_sdk(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> NeMoPlatform:
    """Build a general-purpose sync SDK handle.

    Lower-level than :func:`get_task_sdk` — callers choose their own auth
    mode.  Useful for plugins that don't use :func:`run_task` (e.g.
    ``safe-synthesizer``).
    """
    return _resolve_provider().get_platform_sdk(
        as_service=as_service,
        internal=internal,
        on_behalf_of=on_behalf_of,
    )


def get_async_platform_sdk(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> AsyncNeMoPlatform:
    """Build a general-purpose async SDK handle.

    Used by middleware and controllers that run inside the platform
    service process and need an async client.
    """
    return _resolve_provider().get_async_platform_sdk(
        as_service=as_service,
        internal=internal,
        on_behalf_of=on_behalf_of,
    )


def get_forwarding_headers(sdk: NeMoPlatform | AsyncNeMoPlatform) -> dict[str, str]:
    """Extract the platform headers an SDK would send on outbound requests.

    Returns the ``X-NMP-*`` and trace-propagation headers that *sdk* was
    configured with.  Use this when forwarding identity and observability
    context through a non-SDK HTTP client (e.g. LangChain's ``ChatNVIDIA``).

    The returned dict is a shallow copy — callers may mutate it freely.

    Args:
        sdk: A :class:`~nemo_platform.NeMoPlatform` or
            :class:`~nemo_platform.AsyncNeMoPlatform` instance.  For
            per-request headers, pass a request-scoped SDK built with
            ``sdk.with_options(set_default_headers=...)``.
    """
    # _custom_headers holds the headers passed at construction time
    # (service principal, internal marker, on-behalf-of, OTEL, etc.)
    # — everything the platform SDK factory injects.
    return dict(sdk._custom_headers)


__all__ = [
    "DefaultTaskSDKProvider",
    "TaskSDKProvider",
    "get_async_platform_sdk",
    "get_forwarding_headers",
    "get_platform_sdk",
    "get_task_sdk",
    "set_task_sdk_provider",
]
