# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx
from fastapi import APIRouter
from nemo_platform_plugin.authz import (
    CallerKind,
    Permission,
    path_rule,
)
from nemo_platform_plugin.authz_discovery import (
    _derive_service_contribution,
    clear_plugin_authz_cache,
    discover_authz_contributions,
)
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.scheduler import NemoJobScheduler
from nemo_platform_plugin.service import NemoService, RouterSpec


class _ExampleSubmitJob(NemoJob):
    name = "example-submit"
    description = "Job used to verify authenticated remote submit."

    def run(self, config: dict) -> dict:
        return config


_ExampleSubmitJob.__module__ = "example_plugin.jobs.example_submit"


class _FakeEntryPoint:
    """Minimal EntryPoint stand-in: discover_plugin_authz only calls ``.load()`` / reads ``.name``."""

    def __init__(self, name: str, loader) -> None:
        self.name = name
        self.value = f"test:{name}"
        self._loader = loader

    def load(self):
        return self._loader()


def test_derive_contribution_composes_mounted_path(monkeypatch) -> None:
    """A service's @path_rule routes derive to the final /apis/<name>/<prefix> paths.

    The permission catalog (id -> description) is derived from the Permission objects on the
    routes — there is no separate declaration.
    """
    router = APIRouter()

    @router.get("/v2/workspaces/{workspace}/items/{name}")
    @path_rule(
        callers=[CallerKind.PRINCIPAL],
        permissions=[Permission("example.items.read", "Read example items")],
        scopes=["example:read"],
    )
    async def get_item(workspace: str, name: str) -> dict[str, str]:
        return {"name": name}

    class _Svc(NemoService):
        name = "example"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_entry_points",
        lambda group: {"example": _FakeEntryPoint("example", lambda: _Svc)},
    )
    clear_plugin_authz_cache()
    try:
        contribs = discover_authz_contributions()
    finally:
        clear_plugin_authz_cache()

    assert len(contribs) == 1
    contrib = contribs[0]
    assert contrib.permissions == {"example.items.read": "Read example items"}

    path = "/apis/example/v2/workspaces/{workspace}/items/{name}"
    assert set(contrib.endpoints[path]) == {"get"}
    binding = contrib.endpoints[path]["get"]
    assert binding.permissions == ["example.items.read"]
    assert binding.scopes == ["example:read"]
    assert binding.callers == ["principal"]


def test_derive_service_only_route_emits_service_principal_callers() -> None:
    router = APIRouter()

    @router.post("/v2/internal/sync")
    @path_rule(callers=[CallerKind.SERVICE_PRINCIPAL])
    async def sync() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems, _warnings = _derive_service_contribution(_Svc())
    assert problems == []
    binding = contrib.endpoints["/apis/svc/v2/internal/sync"]["post"]
    assert binding.callers == ["service_principal"]
    assert binding.permissions == []


def test_derive_unions_callers_across_rules_with_shared_permissions() -> None:
    router = APIRouter()
    svc_read = Permission("svc.read", "Read")

    @router.get("/v2/y")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[svc_read])
    @path_rule(callers=[CallerKind.SERVICE_PRINCIPAL], permissions=[svc_read])
    async def y() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems, _warnings = _derive_service_contribution(_Svc())
    assert problems == []
    binding = contrib.endpoints["/apis/svc/v2/y"]["get"]
    assert binding.callers == ["principal", "service_principal"]
    assert binding.permissions == ["svc.read"]


def test_derive_denies_route_with_or_of_distinct_permission_sets() -> None:
    """v1 cannot represent (principal & permA) OR (service & permB): the route is denied
    (fail-closed) with a recorded problem, without crashing the rest of the plugin."""
    router = APIRouter()

    @router.get("/v2/z")
    @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[Permission("z.read", "Read z")])
    @path_rule(callers=[CallerKind.SERVICE_PRINCIPAL], permissions=[Permission("z.internal", "Internal z")])
    async def z() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems, _warnings = _derive_service_contribution(_Svc())
    assert contrib.endpoints["/apis/svc/v2/z"]["get"].deny is True
    assert any("distinct permission sets" in p for p in problems)


def test_derive_emits_deny_for_unruled_route() -> None:
    router = APIRouter()

    @router.get("/v2/unruled")
    async def unruled() -> None: ...

    class _Svc(NemoService):
        name = "svc"

        def get_routers(self) -> list[RouterSpec]:
            return [RouterSpec(router)]

    contrib, problems, _warnings = _derive_service_contribution(_Svc())
    # Unruled routes are explicit-deny (fail-closed), never omitted.
    assert contrib.endpoints["/apis/svc/v2/unruled"]["get"].deny is True
    assert any("no @path_rule" in p for p in problems)


def test_submit_remote_forwards_authorization_header() -> None:
    """Authenticated CLI submit passes Authorization to the protected job route."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json={"id": "job-123", "status": "queued"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    scheduler = NemoJobScheduler()

    result = scheduler.submit_remote(
        _ExampleSubmitJob,
        {"foo": "bar"},
        base_url="https://nmp.test",
        workspace="ws-a",
        headers={"Authorization": "Bearer test-token"},
        http_client=client,
    )

    assert result == {"id": "job-123", "status": "queued"}
    assert captured.get("authorization") == "Bearer test-token"
