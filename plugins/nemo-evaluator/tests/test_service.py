# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the evaluator plugin service surface."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator.service import EvaluatorPluginService


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


def test_service_health_route_mounts_with_valid_prefix() -> None:
    app = FastAPI()
    service = EvaluatorPluginService()
    for spec in service.get_routers():
        app.include_router(spec.router, prefix=spec.prefix)

    response = TestClient(app).get("/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "plugin": "evaluator",
        "status": "ok",
        "mode": "sdk-backed-job-scaffold",
        "jobs": ["evaluator.evaluate", "evaluator.agent-evaluate"],
    }


def test_service_mounts_evaluator_job_collection_at_sdk_route() -> None:
    app = FastAPI()
    service = EvaluatorPluginService()
    for spec in service.get_routers():
        app.include_router(spec.router, prefix=spec.prefix)

    route_paths = _route_paths(app)

    assert "/v2/workspaces/{workspace}/evaluate/jobs" in route_paths
