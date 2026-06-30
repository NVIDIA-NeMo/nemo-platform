# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_automodel_plugin.contributor import AutomodelContributor
from nemo_customizer.router import CustomizationRouterService


def _route_paths(app: FastAPI) -> set[str]:
    """Collect all route paths, compatible with FastAPI 0.138+ _IncludedRouter."""
    paths: set[str] = set()
    queue = list(app.routes)
    while queue:
        route = queue.pop()
        if hasattr(route, "path"):
            paths.add(route.path)
        fn = getattr(route, "effective_candidates", None)
        if callable(fn):
            queue.extend(fn())  # type: ignore[arg-type]
    return paths


def _make_automodel_app() -> FastAPI:
    app = FastAPI()
    for spec in AutomodelContributor().get_routers():
        app.include_router(spec.router, prefix=spec.prefix, tags=[spec.tag] if spec.tag else None)
    return app


def test_automodel_healthz_under_workspace() -> None:
    client = TestClient(_make_automodel_app())
    response = client.get("/v2/workspaces/test-ws/automodel/healthz")
    assert response.status_code == 200
    assert response.json() == {"backend": "automodel", "status": "ok"}


def test_automodel_jobs_collection_path() -> None:
    paths = _route_paths(_make_automodel_app())
    assert "/v2/workspaces/{workspace}/automodel/jobs" in paths


def test_customization_router_merges_automodel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_customizer.router.discover_customization_contributors",
        lambda: {"automodel": AutomodelContributor()},
    )
    service = CustomizationRouterService()
    app = FastAPI()
    for spec in service.get_routers():
        prefix = spec.prefix or ""
        app.include_router(spec.router, prefix=prefix)

    client = TestClient(app)
    assert client.get("/healthz").json()["contributors"] == ["automodel"]
    assert client.get("/v2/workspaces/ws-a/automodel/healthz").status_code == 200


def test_workspace_isolation_list_uses_path_segment() -> None:
    """Job routes are under ``/v2/workspaces/{workspace}/automodel/jobs`` — distinct per workspace."""
    app = _make_automodel_app()
    paths = _route_paths(app)
    assert "/v2/workspaces/{workspace}/automodel/jobs" in paths
    assert "/v2/workspaces/{workspace}/automodel/healthz" in paths
