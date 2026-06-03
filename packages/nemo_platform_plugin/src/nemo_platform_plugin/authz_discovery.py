# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discover plugin authorization contributions for policy merge."""

from __future__ import annotations

import inspect
import logging
from functools import cache
from typing import Any, Callable

from nemo_platform_plugin.authz import AuthzContribution, AuthzEndpointMethod

logger = logging.getLogger(__name__)

AUTHZ_GROUP = "nemo.authz"

AuthzContributor = Callable[[], AuthzContribution] | type[Any]


def _load_authz_contribution(loaded: AuthzContributor, source: str) -> AuthzContribution | None:
    try:
        if isinstance(loaded, type):
            if hasattr(loaded, "get_authz_contribution"):
                result = _invoke_get_authz_contribution(loaded)
            else:
                instance = loaded()
                result = _invoke_get_authz_contribution(instance)
        elif callable(loaded):
            result = loaded()
        else:
            logger.warning("Authz entry %s is not callable or a class — skipping", source)
            return None
    except Exception:
        logger.warning("Failed to load authz contribution from %s — skipping", source, exc_info=True)
        return None

    if result is None:
        return None
    if isinstance(result, AuthzContribution):
        return result
    if isinstance(result, dict):
        return AuthzContribution(
            permissions=result.get("permissions") or {},
            endpoints={
                path: {method: _method_from_dict(spec) for method, spec in methods.items() if isinstance(spec, dict)}
                for path, methods in (result.get("endpoints") or {}).items()
                if isinstance(methods, dict)
            },
            role_permissions=result.get("role_permissions") or {},
        )
    logger.warning("Authz contribution from %s has unexpected type %r — skipping", source, type(result))
    return None


def _invoke_get_authz_contribution(item: Any) -> AuthzContribution | dict[str, Any] | None:
    """Call ``get_authz_contribution`` on a service class or contributor instance."""
    getter = getattr(item, "get_authz_contribution", None)
    if not callable(getter):
        return None
    if isinstance(item, type):
        # discover_services() yields classes — must be @classmethod on NemoService.
        return getter()
    return getter()


def _method_from_dict(spec: dict[str, Any]) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(
        permissions=list(spec.get("permissions") or []),
        scopes=list(spec["scopes"]) if spec.get("scopes") is not None else None,
    )


def _collect_from_plugin_surface(
    items: dict[str, Any],
    surface: str,
) -> list[AuthzContribution]:
    contributions: list[AuthzContribution] = []
    for key, item in items.items():
        if not hasattr(item, "get_authz_contribution"):
            continue
        if isinstance(item, type):
            method = inspect.getattr_static(item, "get_authz_contribution", None)
            if method is None or not isinstance(method, classmethod):
                # Only classmethods are valid on NemoService subclasses (no instance).
                continue
        try:
            result = _invoke_get_authz_contribution(item)
        except TypeError as exc:
            logger.warning(
                "Authz on %s %r must be a @classmethod (discover_services loads classes): %s",
                surface,
                key,
                exc,
            )
            continue
        except Exception:
            logger.warning(
                "Failed to get authz contribution from %s %r — skipping",
                surface,
                key,
                exc_info=True,
            )
            continue
        if result is None:
            continue
        if isinstance(result, AuthzContribution):
            contributions.append(result)
        elif isinstance(result, dict):
            loaded = _load_authz_contribution(lambda: result, source=f"{surface}:{key}")
            if loaded is not None:
                contributions.append(loaded)
        else:
            logger.warning(
                "Authz contribution from %s %r has unexpected type %r — skipping",
                surface,
                key,
                type(result),
            )
    return contributions


@cache
def discover_authz_contributions() -> list[AuthzContribution]:
    """Collect authz contributions from entry points and plugin surfaces.

    Sources (in order):

    1. ``nemo.authz`` entry points (callable or class)
    2. ``nemo.services`` classes implementing :meth:`get_authz_contribution`
    """
    from nemo_platform_plugin.discovery import discover_entry_points, discover_services

    contributions: list[AuthzContribution] = []

    for ep_name, ep in discover_entry_points(AUTHZ_GROUP).items():
        try:
            loaded = ep.load()
            contrib = _load_authz_contribution(loaded, source=f"nemo.authz:{ep_name}")
            if contrib is not None:
                contributions.append(contrib)
                logger.debug("Loaded authz contribution from nemo.authz:%s", ep_name)
        except Exception:
            logger.warning("Failed to load nemo.authz entry %r — skipping", ep_name, exc_info=True)

    contributions.extend(_collect_from_plugin_surface(discover_services(), surface="nemo.services"))

    return contributions


def discover_authz_contribution_dicts() -> list[dict[str, Any]]:
    """Return contributions as dicts for :func:`nmp.common.auth.authz_merge.merge_authz_contributions`."""
    return [c.to_dict() for c in discover_authz_contributions()]
