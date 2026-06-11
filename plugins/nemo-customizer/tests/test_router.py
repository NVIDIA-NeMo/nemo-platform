# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import ClassVar

import pytest
import typer
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from nemo_customizer.router import (
    CustomizationRouterError,
    CustomizationRouterService,
    merge_router_dependencies,
)
from nemo_platform_plugin.authz import authz_for_workspace_job_collection
from nemo_platform_plugin.service import RouterSpec


class _FakeContributor:
    name: ClassVar[str] = "fake"
    dependencies: ClassVar[list[str]] = ["studio"]

    def get_routers(self) -> list[RouterSpec]:
        router = APIRouter()

        @router.get("/ping")
        async def ping() -> dict[str, str]:
            return {"backend": "fake"}

        return [
            RouterSpec(
                router=router,
                prefix="/v2/workspaces/{workspace}/fake",
                tag="Fake",
            ),
        ]

    def get_cli(self) -> typer.Typer:
        app = typer.Typer()

        @app.command("info")
        def info() -> None:
            typer.echo("fake")

        return app


def test_merge_router_dependencies_unions_contributor_deps() -> None:
    deps = merge_router_dependencies({"fake": _FakeContributor()})
    assert "studio" in deps
    assert "jobs" in deps


def test_router_sets_merged_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {"fake": _FakeContributor()},
    )
    CustomizationRouterService()
    assert "studio" in CustomizationRouterService.dependencies


def test_router_raises_without_contributors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {},
    )
    with pytest.raises(CustomizationRouterError, match="no contributors"):
        CustomizationRouterService()


def test_router_merges_contributor_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {"fake": _FakeContributor()},
    )
    service = CustomizationRouterService()
    app = FastAPI()
    for spec in service.get_routers():
        if spec.prefix:
            app.include_router(spec.router, prefix=spec.prefix)
        else:
            app.include_router(spec.router)

    client = TestClient(app)
    assert client.get("/healthz").json()["contributors"] == ["fake"]
    assert client.get("/v2/workspaces/ws-a/fake/ping").json() == {"backend": "fake"}


def test_prefix_collision_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DupA(_FakeContributor):
        name = "a"

    class _DupB(_FakeContributor):
        name = "b"

    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {"a": _DupA(), "b": _DupB()},
    )
    with pytest.raises(CustomizationRouterError, match="collision"):
        CustomizationRouterService()


def test_shared_parent_prefix_with_disjoint_routes_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two contributors mounting at the same parent prefix is fine as long as their
    actual routes underneath don't collide. This is the automodel + unsloth case:
    both register their jobs router at ``/v2/workspaces/{workspace}`` and add a
    backend-scoped collection path via ``job_collection_path_for``.
    """

    def _make_contributor(backend_name: str) -> object:
        class _Contributor:
            name: ClassVar[str] = backend_name
            dependencies: ClassVar[list[str]] = []

            def get_routers(self) -> list[RouterSpec]:
                router = APIRouter()

                @router.post(f"/{backend_name}/jobs")
                async def submit() -> dict[str, str]:
                    return {"backend": backend_name}

                return [
                    RouterSpec(
                        router=router,
                        prefix="/v2/workspaces/{workspace}",
                        tag=backend_name.title(),
                    ),
                ]

            def get_cli(self) -> typer.Typer:
                return typer.Typer()

        return _Contributor()

    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {"automodel": _make_contributor("automodel"), "unsloth": _make_contributor("unsloth")},
    )
    # Should not raise.
    service = CustomizationRouterService()
    assert sorted(service._contributors.keys()) == ["automodel", "unsloth"]


def test_get_authz_contribution_merges_backend_contributors(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AutomodelContributor:
        name: ClassVar[str] = "automodel"
        dependencies: ClassVar[list[str]] = []

        def get_authz_contribution(self) -> object:
            return authz_for_workspace_job_collection(
                api_area="customization",
                collection_suffix="/automodel/jobs",
                permission_prefix="customization.automodel.jobs",
                include_healthz=True,
                healthz_suffix="/automodel/healthz",
            )

        def get_routers(self) -> list[RouterSpec]:
            return []

        def get_cli(self) -> typer.Typer:
            return typer.Typer()

    class _UnslothContributor:
        name: ClassVar[str] = "unsloth"
        dependencies: ClassVar[list[str]] = []

        def get_authz_contribution(self) -> object:
            return authz_for_workspace_job_collection(
                api_area="customization",
                collection_suffix="/unsloth/jobs",
                permission_prefix="customization.unsloth.jobs",
            )

        def get_routers(self) -> list[RouterSpec]:
            return []

        def get_cli(self) -> typer.Typer:
            return typer.Typer()

    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {"automodel": _AutomodelContributor(), "unsloth": _UnslothContributor()},
    )

    contrib = CustomizationRouterService.get_authz_contribution()
    assert contrib is not None
    assert "/apis/customization/healthz" in contrib.endpoints
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/jobs" in contrib.endpoints
    assert "/apis/customization/v2/workspaces/{workspace}/unsloth/jobs" in contrib.endpoints
    assert "customization.automodel.jobs.create" in contrib.permissions
    assert "customization.unsloth.jobs.create" in contrib.permissions


def test_get_authz_contribution_returns_none_without_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {},
    )
    assert CustomizationRouterService.get_authz_contribution() is None
