# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authorization policy for NeMo Platform plugins.

A plugin attaches :func:`path_rule` rules to its route handlers, referencing
:class:`Permission` objects from a typed :class:`PermissionSet`. The platform derives
the normalized policy — the permission catalog (id + description), the per-endpoint
bindings, and the namespace — *entirely from the routes* (see
:mod:`nemo_platform_plugin.authz_discovery`) when the OPA bundle is built; it can also be
materialized into ``static-authz.yaml`` via ``auth-tools sync-plugins``.

There is no separate permission declaration to keep in sync: the permission *is* the
object referenced on the route, and it carries its own description. The only thing a
service declares apart from its routes is the optional escape hatch
:meth:`NemoService.extra_permissions` — for permissions that are not 1:1 with a route
(e.g. checked in middleware).

Example::

    from fastapi import APIRouter
    from nemo_platform_plugin.authz import CallerKind, PermissionSet, path_rule, perm
    from nemo_platform_plugin.service import NemoService, RouterSpec

    class ExamplePerms(PermissionSet, namespace="example"):
        READ = perm("Read example items")  # -> Permission("example.read", ...)

    router = APIRouter()

    @router.get("/v2/workspaces/{workspace}/items/{name}")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[ExamplePerms.READ])
    async def get_item(workspace: str, name: str) -> dict: ...

    class ExampleService(NemoService):
        name = "example"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

# ---------------------------------------------------------------------------
# Plugin authoring API: a typed permission vocabulary + path rules.
#
# Plugins declare permissions as ``Permission`` constants (typically grouped in a
# ``PermissionSet``) and attach ``PathRule``s to route handlers with ``@path_rule``,
# referencing those constants. The platform derives the wire-format
# ``AuthzContribution`` (below) from the routes at startup — there is no separate
# permission list. See the "Plugin Authz Decorator Spec".
# ---------------------------------------------------------------------------


class CallerKind(StrEnum):
    """Who a route is intended for — a PDP *subject attribute*, not a permission.

    Plugin routes are ``PRINCIPAL`` (a normal authenticated user) or
    ``SERVICE_PRINCIPAL`` (a caller whose id is prefixed ``service:``). There is
    intentionally no ``ANON``: the only genuinely public routes are core
    infrastructure, hardcoded as a bypass in the PEP.
    """

    PRINCIPAL = "principal"
    SERVICE_PRINCIPAL = "service_principal"


@dataclass(frozen=True)
class Permission:
    """A service-owned permission: a stable id and a required human description.

    The id is the wire value (what path rules and roles reference); the description is
    the one piece of authz data that cannot be derived from anything else, so it rides
    on the permission itself rather than in a parallel list. ``str(permission)`` is the
    id, so a ``Permission`` can be used wherever the wire string is expected.
    """

    id: str
    description: str

    def __str__(self) -> str:
        return self.id


# Permission ids are two or more dot-separated lowercase segments (digits and internal
# hyphens allowed), e.g. ``models.create`` / ``auditor.configs.read``. This mirrors the
# platform wire contract (``nmp.common.auth.authz_format.PERMISSION_ID_PATTERN``); it is
# duplicated here, not imported, so the plugin SDK carries no nmp_common dependency and
# stays usable out of this repo.
_PERMISSION_ID_SEGMENT = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PERMISSION_ID_PATTERN = re.compile(rf"^{_PERMISSION_ID_SEGMENT}(?:\.{_PERMISSION_ID_SEGMENT})+$")


def is_valid_permission_id(permission_id: str) -> bool:
    """Return True if *permission_id* matches the platform permission-id format.

    A valid id is two or more dot-separated lowercase segments (digits and internal
    hyphens allowed), e.g. ``models.create`` or ``auditor.configs.read``.
    """
    return bool(permission_id) and _PERMISSION_ID_PATTERN.fullmatch(permission_id) is not None


@dataclass(frozen=True)
class _PendingPermission:
    """A permission declared inside a :class:`PermissionSet` body before its namespace
    is known. :meth:`PermissionSet.__init_subclass__` resolves it into a
    :class:`Permission` once the namespace is bound."""

    description: str
    suffix: str | None = None


def perm(description: str, *, suffix: str | None = None) -> Any:
    """Declare a permission inside a :class:`PermissionSet` body.

    The id is built as ``<namespace>.<member-name-lowercased>`` unless *suffix* is given
    (use *suffix* for compound ids, e.g. ``perm("...", suffix="configs.create")``). The
    return type is ``Any`` so the class attribute type-checks as a :class:`Permission`
    after ``__init_subclass__`` rewrites it.
    """
    return _PendingPermission(description, suffix)


class PermissionSet:
    """A closed, typed group of permissions under one namespace.

    Subclass with ``namespace=`` and assign ``perm(...)`` members; each becomes a
    :class:`Permission` whose id is ``<namespace>.<member-name-lowercased>`` (or the
    explicit ``suffix``). Referencing a member that doesn't exist is an ``AttributeError``
    at import — a permission typo can't reach the policy layer.

        class WidgetPerms(PermissionSet, namespace="widget"):
            CREATE = perm("Create a widget")   # -> Permission("widget.create", ...)
    """

    namespace: str
    _members: dict[str, Permission]

    def __init_subclass__(cls, *, namespace: str, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.namespace = namespace
        cls._members = {}
        for name, value in list(vars(cls).items()):
            if isinstance(value, _PendingPermission):
                suffix = value.suffix or name.lower()
                resolved = Permission(f"{namespace}.{suffix}", value.description)
                setattr(cls, name, resolved)
                cls._members[name] = resolved

    @classmethod
    def all(cls) -> list[Permission]:
        """Every permission declared on this set (handy for ``extra_permissions``)."""
        return list(cls._members.values())


@dataclass(frozen=True, kw_only=True)
class PathRule:
    """One alternative authorization rule for a route handler.

    Within a rule, ``callers`` are OR'd and ``permissions`` are AND'd. Multiple rules on
    one endpoint are OR'd (any satisfied rule allows access).

    ``method`` and ``path`` are unknown at decoration time and are filled in during
    derivation once the route is mounted (see ``authz_discovery``).
    """

    callers: list[CallerKind]
    permissions: list[Permission] = field(default_factory=list)
    scopes: list[str] | None = None
    method: str | None = None
    path: str | None = None


# Attribute used to stash the (OR-combined) ``PathRule``s on a route handler.
# Mutated in place — the function is never wrapped — so ``route.endpoint``
# identity survives FastAPI ``include_router(prefix=...)`` rebasing, which
# rebuilds ``APIRoute`` objects but passes the endpoint through by identity.
PATH_RULES_ATTR = "__nemo_path_rules__"

_F = TypeVar("_F", bound=Callable[..., Any])


def path_rule(
    *,
    callers: list[CallerKind],
    permissions: list[Permission] | None = None,
    scopes: list[str] | None = None,
) -> Callable[[_F], _F]:
    """Attach an authorization rule to a route handler.

    Stacking ``@path_rule`` on the same handler adds alternative (OR) rules. The
    handler is returned **unchanged** (same object, same signature): the rule is
    stored on the function itself so it survives router rebasing.

    Args:
        callers: Non-empty list of caller kinds this rule applies to (OR'd).
        permissions: :class:`Permission` objects the caller must hold (AND'd). May be
            empty for authenticated-but-permissionless routes.
        scopes: Optional normalized NeMo scopes (``area:verb``).

    Raises:
        ValueError: if *callers* is empty or contains an unknown caller kind.
        TypeError: if any *permissions* entry is not a :class:`Permission` (e.g. a bare
            string) — caught at decoration so a typo can't silently reach the policy layer.
    """
    resolved_callers = [CallerKind(c) for c in callers]
    if not resolved_callers:
        raise ValueError("@path_rule requires at least one caller kind")
    resolved_permissions = list(permissions or [])
    for p in resolved_permissions:
        if not isinstance(p, Permission):
            raise TypeError(
                f"@path_rule permissions must be Permission objects, got {type(p).__name__} ({p!r}). "
                f"Reference a PermissionSet member (e.g. MyPerms.READ) rather than a bare string."
            )
    rule = PathRule(
        callers=resolved_callers,
        permissions=resolved_permissions,
        scopes=list(scopes) if scopes is not None else None,
    )

    def decorate(func: _F) -> _F:
        rules = func.__dict__.get(PATH_RULES_ATTR)
        if rules is None:
            rules = []
            setattr(func, PATH_RULES_ATTR, rules)
        rules.append(rule)
        return func

    return decorate


def get_path_rules(func: Callable[..., Any]) -> list[PathRule]:
    """Return the ``PathRule``s attached to *func* by :func:`path_rule` (empty if none)."""
    return list(getattr(func, PATH_RULES_ATTR, []))


def validate_caller_strings(callers: list[str] | None, *, context: str) -> None:
    """Validate wire-format caller kinds. Absence (``None``) is allowed (⇒ PRINCIPAL).

    The valid set is derived from :class:`CallerKind` rather than hardcoded, so it
    cannot drift from the enum.

    Raises:
        ValueError: if any value is not a known :class:`CallerKind`.
    """
    if callers is None:
        return
    valid = {c.value for c in CallerKind}
    for c in callers:
        if c not in valid:
            raise ValueError(f"Invalid caller kind {c!r} in {context}: expected one of {sorted(valid)}.")


@dataclass(frozen=True)
class AuthzEndpointMethod:
    """One HTTP method binding for an API route."""

    permissions: list[str]
    scopes: list[str] | None = None
    callers: list[str] | None = None
    """Allowed caller kinds (:class:`CallerKind` values). ``None`` ⇒ PRINCIPAL (default)."""

    deny: bool = False
    """When True the route is unconditionally denied — the fail-closed marker for an
    unruled or invalid plugin route. The PDP denies it outright, overriding every allow
    rule (including the service ``*`` wildcard and the PlatformAdmin bypass), so an
    un-annotated route can never fall through to the ``service:`` no-match bypass."""


@dataclass
class AuthzContribution:
    """Authorization data contributed by a plugin."""

    permissions: dict[str, str] = field(default_factory=dict)
    """Flat registry entries: ``permission_id`` → human-readable description."""

    endpoints: dict[str, dict[str, AuthzEndpointMethod]] = field(default_factory=dict)
    """Full API paths (``/apis/...``) → lower-case HTTP method → spec."""

    role_permissions: dict[str, list[str]] = field(default_factory=dict)
    """Optional explicit role → permission grants (merged with defaults)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for :func:`nmp.common.auth.authz_merge.merge_authz_contributions`."""
        return {
            "permissions": dict(self.permissions),
            "endpoints": {
                path: {
                    method: {
                        "permissions": spec.permissions,
                        **({"scopes": spec.scopes} if spec.scopes is not None else {}),
                        **({"callers": spec.callers} if spec.callers is not None else {}),
                        **({"deny": True} if spec.deny else {}),
                    }
                    for method, spec in methods.items()
                }
                for path, methods in self.endpoints.items()
            },
            "role_permissions": {role: list(perms) for role, perms in self.role_permissions.items()},
        }


def scopes_for(api_area: str, write: bool) -> list[str]:
    """Normalized NeMo scopes for a route: the api-area scope plus the platform scope."""
    verb = "write" if write else "read"
    return [f"{api_area}:{verb}", f"platform:{verb}"]
