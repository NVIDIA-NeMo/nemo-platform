# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Derive plugin authorization contributions from the ``NemoService`` route surface.

Plugins attach :func:`~nemo_platform_plugin.authz.path_rule` rules to route handlers,
referencing :class:`~nemo_platform_plugin.authz.Permission` constants. This module
instantiates each discovered ``NemoService``, walks its mounted routes — computing the
same ``/apis/<name>/<prefix>`` paths the platform mounts at runtime — reads the
function-attached :class:`~nemo_platform_plugin.authz.PathRule`\\ s, and builds the
wire-format :class:`~nemo_platform_plugin.authz.AuthzContribution` consumed by the OPA
bundle builder and ``auth-tools sync-plugins``.

The permission catalog (ids + descriptions) and the service namespace are derived
*entirely from the routes* (plus the optional :meth:`NemoService.extra_permissions`
hatch). There is no separately-declared permission list: the permission is the object
referenced on the route, and it carries its own description.

Path composition mirrors production: the platform runner mounts each service app at
``/apis/<service.name>`` and the service app includes each ``RouterSpec`` router at its
``prefix`` (see ``nmp.platform_runner.server`` and ``nmp.common.service.base``). We
re-create that composition with a throwaway router so FastAPI computes the final paths —
including prefix joins and ``{param:path}`` wildcards — exactly as it does at runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cache
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute
from nemo_platform_plugin.authz import (
    AuthzContribution,
    AuthzEndpointMethod,
    CallerKind,
    PathRule,
    Permission,
    get_path_rules,
)
from nemo_platform_plugin.service import NemoService

logger = logging.getLogger(__name__)


def _method_from_dict(spec: dict[str, Any]) -> AuthzEndpointMethod:
    """Parse a serialized endpoint-method dict back into :class:`AuthzEndpointMethod`.

    This is the single chokepoint that decides which wire fields are preserved; unknown
    keys are dropped. Kept as the canonical inverse of ``AuthzContribution.to_dict`` for
    round-trip validation and bundle-side parsing.
    """
    return AuthzEndpointMethod(
        permissions=list(spec.get("permissions") or []),
        scopes=list(spec["scopes"]) if spec.get("scopes") is not None else None,
        callers=list(spec["callers"]) if spec.get("callers") is not None else None,
        deny=bool(spec.get("deny", False)),
    )


def _wire_callers(rules: list[PathRule]) -> list[str] | None:
    """Union the caller kinds across an endpoint's (OR'd) rules into the wire list.

    Returns ``None`` when no rule declares callers (the route falls back to the PRINCIPAL
    default and the Rego layer adds no caller-kind restriction).
    """
    kinds = {c.value if isinstance(c, CallerKind) else str(c) for rule in rules for c in rule.callers}
    return sorted(kinds) if kinds else None


def _collapse_rules(
    rules: list[PathRule], *, path: str, method: str, service: str
) -> tuple[list[Permission], list[str] | None, list[str] | None]:
    """Collapse the (OR'd) ``PathRule``\\ s on one ``(path, method)`` into one binding.

    v1 supports OR across rules only in the **caller** dimension: caller kinds are unioned,
    but ``permissions`` and ``scopes`` must agree across rules. The single-slot wire format
    (one AND'd ``permissions`` list per method) and the Rego permission check cannot
    represent an OR of *distinct* permission sets, so that case is rejected loudly rather
    than silently mis-authorized.

    Returns ``(permissions, scopes, callers)`` for the representative rule.
    """
    perm_sets = {frozenset(p.id for p in rule.permissions) for rule in rules}
    if len(perm_sets) > 1:
        raise ValueError(
            f"{service}: {method.upper()} {path} has @path_rule rules with differing "
            f"permissions ({[sorted(p) for p in perm_sets]}). v1 cannot represent an OR of "
            f"distinct permission sets — use one rule with shared permissions, or a single "
            f"rule listing multiple callers."
        )
    scope_sets = {None if rule.scopes is None else frozenset(rule.scopes) for rule in rules}
    if len(scope_sets) > 1:
        raise ValueError(
            f"{service}: {method.upper()} {path} has @path_rule rules with differing scopes — "
            f"all rules on one endpoint must declare the same scopes."
        )

    representative = rules[0]
    return (
        list(representative.permissions),
        list(representative.scopes) if representative.scopes is not None else None,
        _wire_callers(rules),
    )


@dataclass
class PluginAuthzResult:
    """One plugin's derived authz, before the bundle applies its fail-mode policy.

    ``problems`` is empty for a clean plugin. A non-empty list means the plugin's authz is
    invalid (unruled routes, OR of distinct permission sets, conflicting descriptions, a
    permission outside the service's namespace, or a load failure); the affected routes are
    already emitted as explicit DENY bindings in ``contribution`` (fail-closed), and the
    bundle decides — via ``authz.on_invalid_plugin`` — whether to keep just those denies
    (``deny_route``), deny the whole plugin (``quarantine``), or refuse to build the bundle
    (``hard_fail``).
    """

    key: str
    contribution: AuthzContribution
    problems: list[str]
    mount_name: str = ""
    """The ``/apis/<mount_name>`` segment the runner mounts this service at (its
    ``NemoService.name``). Captured so the degraded-plugin namespace fence can cover the real
    mount path even when it diverges from the entry-point ``key`` — the ``name == key``
    invariant is only warned, not enforced (see ``discover_services``)."""


def _deny_binding() -> AuthzEndpointMethod:
    """A wire binding that the PDP denies unconditionally (fail-closed marker)."""
    return AuthzEndpointMethod(permissions=[], deny=True)


def _infer_namespace(permission_ids: list[str]) -> str | None:
    """Infer the service's permission namespace as the common dot-segment prefix of its ids.

    The namespace is the prefix every permission id shares, never including a trailing
    action segment (so a lone ``x.read`` infers ``x``, and ``agents.agents.*`` +
    ``agents.suite.*`` infer ``agents``). This replaces the previously-*declared*
    ``permission_namespace`` with a *derived* one while preserving the "one service, one
    namespace" invariant.

    Returns:
        - The inferred namespace string.
        - ``""`` when the service declares no permissions (only permissionless routes).
        - ``None`` when the ids don't share a first segment or one lacks a namespace —
          a malformed plugin whose routes the caller must fail closed.
    """
    if not permission_ids:
        return ""
    id_segments = [pid.split(".") for pid in permission_ids]
    common = id_segments[0]
    for segments in id_segments[1:]:
        shared = 0
        while shared < len(common) and shared < len(segments) and common[shared] == segments[shared]:
            shared += 1
        common = common[:shared]
    max_len = min(len(segments) for segments in id_segments) - 1  # never include an action segment
    common = common[: min(len(common), max_len)]
    if not common:
        return None
    return ".".join(common)


def _register_permission(catalog: dict[str, Permission], perm: Permission, problems: list[str]) -> None:
    """Record *perm* in *catalog*, flagging a missing or conflicting description.

    A description problem is metadata-only (it never denies a route — the route still
    requires the right permission), so it is reported but does not change enforcement.
    """
    if not perm.description:
        problems.append(f"permission {perm.id!r} is missing a description")
    previous = catalog.get(perm.id)
    if previous is not None and previous.description != perm.description:
        problems.append(
            f"permission {perm.id!r} defined with conflicting descriptions: "
            f"{previous.description!r} != {perm.description!r}"
        )
    catalog.setdefault(perm.id, perm)


def _derive_service_contribution(service: NemoService) -> tuple[AuthzContribution, list[str]]:
    """Derive one plugin's wire contribution and collect any authz problems.

    Every mounted route must carry a valid ``@path_rule``. A route that doesn't — unruled,
    or an unrepresentable OR of distinct permission sets — is emitted as an explicit DENY
    binding (never omitted), so it can never fall through to the ``service:`` no-match
    bypass. The permission catalog and namespace are derived from the permissions the routes
    reference plus ``extra_permissions()``; if those permissions don't share one namespace
    the whole plugin fails closed. The returned problem list drives the bundle fail-mode.
    """
    problems: list[str] = []
    catalog: dict[str, Permission] = {}

    # Re-create the runtime mount: /apis/<name> + RouterSpec.prefix + route path.
    composed = APIRouter()
    for spec in service.get_routers():
        composed.include_router(spec.router, prefix=f"/apis/{service.name}{spec.prefix}")

    # Pass 1: walk routes, collapse OR'd rules, and collect referenced permissions.
    # ``bindings`` holds the tentative allow binding per (path, method); unruled / invalid
    # routes are recorded as None and become DENY regardless of namespace validity.
    bindings: dict[str, dict[str, AuthzEndpointMethod | None]] = {}
    for route in composed.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(route.methods or set())
        rules = get_path_rules(route.endpoint)

        binding: AuthzEndpointMethod | None
        if not rules:
            binding = None
            problems.append(f"{route.path} ({', '.join(methods) or 'no methods'}) has no @path_rule")
        else:
            try:
                permissions, scopes, callers = _collapse_rules(
                    rules, path=route.path, method=methods[0] if methods else "", service=service.name
                )
            except ValueError as exc:
                # A single malformed route denies only itself — it never crashes the plugin
                # (which would empty the whole contribution and fall open).
                binding = None
                problems.append(str(exc))
            else:
                for perm in permissions:
                    _register_permission(catalog, perm, problems)
                binding = AuthzEndpointMethod(
                    permissions=[perm.id for perm in permissions], scopes=scopes, callers=callers
                )

        for http_method in methods:
            bindings.setdefault(route.path, {})[http_method.lower()] = binding

    # Permissions with no 1:1 route (middleware-checked, declared-before-wired). A broken
    # extra_permissions() must NOT abort derivation — that would omit the route bindings and
    # let them fall through the service: bypass. Record it and keep the route-derived authz.
    try:
        extra = service.extra_permissions()
    except Exception as exc:
        extra = []
        problems.append(f"extra_permissions() raised {exc!r}")
    for perm in extra:
        _register_permission(catalog, perm, problems)

    # Pass 2: derive + validate the namespace. A plugin whose permissions don't share one
    # namespace is malformed; fail every route closed and contribute no permissions.
    namespace = _infer_namespace(list(catalog))
    if namespace is None:
        problems.append(f"permissions do not share a single namespace (fail-closed): {sorted(catalog)}")
        denied = {path: {method: _deny_binding() for method in methods} for path, methods in bindings.items()}
        return AuthzContribution(permissions={}, endpoints=denied), problems

    endpoints: dict[str, dict[str, AuthzEndpointMethod]] = {
        path: {method: (binding if binding is not None else _deny_binding()) for method, binding in methods.items()}
        for path, methods in bindings.items()
    }
    permissions = {perm.id: perm.description for perm in catalog.values()}
    return AuthzContribution(permissions=permissions, endpoints=endpoints), problems


@cache
def discover_plugin_authz() -> list[PluginAuthzResult]:
    """Derive per-plugin authz results from every discovered ``nemo.services`` plugin.

    Each service class is instantiated once and its mounted routes inspected — a new
    failure surface (instantiation transitively imports job/function modules and runs
    ``get_routers()``). A plugin that fails to load is recorded as a fully-degraded result
    (a problem, no usable contribution) rather than silently dropped — silent drop would
    omit its routes and let them fall through the ``service:`` bypass once enforcement is on.

    Cached for the process lifetime — call ``discover_plugin_authz.cache_clear()`` in tests
    after changing the installed plugin set.
    """
    from nemo_platform_plugin.discovery import discover_services

    results: list[PluginAuthzResult] = []
    for key, service_cls in discover_services().items():
        # Read the mount name off the class (a ClassVar, available even if instantiation
        # below fails) so the degraded fence can cover /apis/<name>, not just /apis/<key>.
        mount_name = getattr(service_cls, "name", key) or key
        try:
            contribution, problems = _derive_service_contribution(service_cls())
        except Exception as exc:
            logger.warning("Failed to derive authz from nemo.services %r — recording as degraded", key, exc_info=True)
            results.append(
                PluginAuthzResult(
                    key=key,
                    contribution=AuthzContribution(),
                    problems=[f"failed to load plugin: {exc!r}"],
                    mount_name=mount_name,
                )
            )
            continue
        results.append(PluginAuthzResult(key=key, contribution=contribution, problems=problems, mount_name=mount_name))
    return results


def discover_authz_contributions() -> list[AuthzContribution]:
    """Plugin contributions with content (compat shim over :func:`discover_plugin_authz`)."""
    return [r.contribution for r in discover_plugin_authz() if r.contribution.permissions or r.contribution.endpoints]


def discover_authz_contribution_dicts() -> list[dict[str, Any]]:
    """Return contributions as dicts for :func:`nmp.common.auth.authz_merge.merge_authz_contributions`."""
    return [c.to_dict() for c in discover_authz_contributions()]
