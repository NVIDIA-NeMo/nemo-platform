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
    service = CustomizationRouterService()
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
