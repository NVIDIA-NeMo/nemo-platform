# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed derivation: unruled/invalid plugin routes derive to explicit DENY + reported problems."""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from nemo_platform_plugin.authz import (
    AuthzContribution,
    AuthzEndpointMethod,
    CallerKind,
    Permission,
    path_rule,
)
from nemo_platform_plugin.authz_discovery import (
    _derive_service_contribution,
    _method_from_dict,
    discover_plugin_authz,
)
from nemo_platform_plugin.service import NemoService, RouterSpec


def test_deny_field_round_trips_through_wire_format() -> None:
    contrib = AuthzContribution(endpoints={"/x": {"get": AuthzEndpointMethod(permissions=[], deny=True)}})
    serialized = contrib.to_dict()["endpoints"]["/x"]["get"]
    assert serialized["deny"] is True
    assert _method_from_dict(serialized).deny is True
    # Absent deny defaults to False (and is omitted from the wire form).
    assert (
        "deny"
        not in AuthzContribution(endpoints={"/x": {"get": AuthzEndpointMethod(permissions=["a"])}}).to_dict()[
            "endpoints"
        ]["/x"]["get"]
    )
    assert _method_from_dict({"permissions": []}).deny is False


def test_permissions_spanning_multiple_namespaces_fail_closed() -> None:
    """A plugin whose permissions don't share one namespace is malformed: every route is denied
    (fail-closed) and no permissions are contributed."""
    router = APIRouter()

    @router.get("/v2/x")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.x.read", "Read x")])
    async def x() -> None: ...

    @router.get("/v2/y")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("other.y.read", "Read y")])
    async def y() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems = _derive_service_contribution(_Svc())
    assert contrib.endpoints["/apis/svc/v2/x"]["get"].deny is True
    assert contrib.endpoints["/apis/svc/v2/y"]["get"].deny is True
    assert contrib.permissions == {}
    assert any("do not share a single namespace" in p for p in problems)


def test_missing_permission_description_is_reported_but_route_not_denied() -> None:
    router = APIRouter()

    @router.get("/v2/x")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.x.read", "")])
    async def x() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems = _derive_service_contribution(_Svc())
    assert any("missing a description" in p for p in problems)
    # A description problem is metadata-only — the route still requires the right permission.
    assert contrib.endpoints["/apis/svc/v2/x"]["get"].deny is False


def test_conflicting_descriptions_for_same_id_reported() -> None:
    router = APIRouter()

    @router.get("/v2/a")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.read", "Read")])
    async def a() -> None: ...

    @router.get("/v2/b")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.read", "Totally different")])
    async def b() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    _, problems = _derive_service_contribution(_Svc())
    assert any("conflicting descriptions" in p for p in problems)


def test_extra_permissions_adds_non_route_permission_to_catalog() -> None:
    """The escape hatch contributes a permission with no 1:1 route (e.g. middleware-checked)."""
    router = APIRouter()

    @router.get("/v2/x")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.read", "Read")])
    async def x() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

        def extra_permissions(self) -> list[Permission]:
            return [Permission("svc.admin", "Administer svc")]

    contrib, problems = _derive_service_contribution(_Svc())
    assert problems == []
    assert contrib.permissions == {"svc.read": "Read", "svc.admin": "Administer svc"}
    # The extra permission has no endpoint binding.
    assert all("svc.admin" not in m.permissions for methods in contrib.endpoints.values() for m in methods.values())


def test_extra_permissions_failure_is_reported_routes_survive() -> None:
    router = APIRouter()

    @router.get("/v2/x")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.read", "Read")])
    async def x() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

        def extra_permissions(self) -> list[Permission]:
            raise RuntimeError("boom")

    contrib, problems = _derive_service_contribution(_Svc())
    # A broken hatch loses its extras but never invalidates the route-derived authz.
    assert any("extra_permissions() raised" in p for p in problems)
    assert contrib.endpoints["/apis/svc/v2/x"]["get"].deny is False
    assert contrib.endpoints["/apis/svc/v2/x"]["get"].permissions == ["svc.read"]


def test_discover_plugin_authz_reports_unruled_route(monkeypatch: pytest.MonkeyPatch) -> None:
    router = APIRouter()

    @router.get("/v2/unruled")
    async def unruled() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    monkeypatch.setattr("nemo_platform_plugin.discovery.discover_services", lambda: {"svc": _Svc})
    discover_plugin_authz.cache_clear()
    try:
        results = discover_plugin_authz()
    finally:
        discover_plugin_authz.cache_clear()

    assert len(results) == 1
    assert results[0].key == "svc"
    assert results[0].problems
    assert results[0].contribution.endpoints["/apis/svc/v2/unruled"]["get"].deny is True


def test_discover_plugin_authz_records_load_failure_as_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadSvc(NemoService):
        name = "bad"

        def get_routers(self) -> list[RouterSpec]:
            raise RuntimeError("boom")

    monkeypatch.setattr("nemo_platform_plugin.discovery.discover_services", lambda: {"bad": _BadSvc})
    discover_plugin_authz.cache_clear()
    try:
        results = discover_plugin_authz()
    finally:
        discover_plugin_authz.cache_clear()

    # A load failure is recorded as degraded (with no usable contribution), never silently dropped.
    assert len(results) == 1
    assert results[0].key == "bad"
    assert any("failed to load" in p for p in results[0].problems)
    assert results[0].contribution.endpoints == {}


def test_clean_plugin_has_no_problems(monkeypatch: pytest.MonkeyPatch) -> None:
    router = APIRouter()

    @router.get("/v2/items/{name}")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("svc.items.read", "Read items")])
    async def get_item(name: str) -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    monkeypatch.setattr("nemo_platform_plugin.discovery.discover_services", lambda: {"svc": _Svc})
    discover_plugin_authz.cache_clear()
    try:
        results = discover_plugin_authz()
    finally:
        discover_plugin_authz.cache_clear()

    assert results[0].problems == []
    assert results[0].contribution.endpoints["/apis/svc/v2/items/{name}"]["get"].deny is False


def test_malformed_route_denies_only_itself_not_the_plugin() -> None:
    """A route whose rules can't collapse denies only itself — the plugin's other routes survive."""
    router = APIRouter()
    svc_read = Permission("svc.read", "Read")

    @router.get("/v2/bad")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[svc_read])
    @path_rule(callers=[CallerKind.SERVICE_PRINCIPAL], permissions=[Permission("svc.internal", "Internal")])
    async def bad() -> None: ...

    @router.get("/v2/good")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[svc_read])
    async def good() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems = _derive_service_contribution(_Svc())
    assert contrib.endpoints["/apis/svc/v2/bad"]["get"].deny is True
    assert contrib.endpoints["/apis/svc/v2/good"]["get"].deny is False
    assert contrib.endpoints["/apis/svc/v2/good"]["get"].permissions == ["svc.read"]
    assert any("distinct permission sets" in p for p in problems)
