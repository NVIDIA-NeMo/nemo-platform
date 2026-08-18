# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service-surface tests: the war-game job route is mounted and its authz derives cleanly.

These guard the regression where the service exposed runs/manifests but never mounted the job
collection, so ``POST /jobs`` (the Studio "Run war-game" path) 404'd, and the derivation gate that
every route carries a ``@path_rule`` (the OPA bundle fails closed otherwise).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_iron_swarm_plugin.service import IronSwarmPluginService


def test_service_declares_jobs_dependency() -> None:
    assert "jobs" in IronSwarmPluginService().dependencies


def test_service_routes_include_war_game_jobs_path() -> None:
    service = IronSwarmPluginService()
    app = FastAPI()
    for spec in service.get_routers():
        app.include_router(spec.router, prefix=spec.prefix)

    spec = TestClient(app).get("/openapi.json").json()

    assert "/v2/workspaces/{workspace}/jobs" in spec["paths"]
    assert "post" in spec["paths"]["/v2/workspaces/{workspace}/jobs"]
    assert "WarGameJobRequest" in spec["components"]["schemas"]


def test_service_authz_derives_from_routes() -> None:
    """Authz is derived from the ``@path_rule``/``@scope`` stamps on every route (there is no
    ``get_authz_contribution``). Doubles as the derivation gate: the service must derive with no
    problems (every route ruled) and no fail-closed DENY bindings.
    """
    from nemo_platform_plugin.authz_discovery import _derive_service_contribution

    contribution, problems, _warnings = _derive_service_contribution(IronSwarmPluginService())

    assert problems == []
    assert not any(spec.deny for methods in contribution.endpoints.values() for spec in methods.values())

    # Job collection (scope.child("jobs") → iron-swarm.jobs.*) plus route permissions.
    for perm_id in (
        "iron-swarm.jobs.create",
        "iron-swarm.jobs.list",
        "iron-swarm.runs.list",
        "iron-swarm.runs.events.write",
        "iron-swarm.manifests.write",
        "iron-swarm.manifests.inspect",
    ):
        assert perm_id in contribution.permissions

    base = "/apis/iron-swarm/v2/workspaces/{workspace}"
    assert contribution.endpoints[f"{base}/jobs"]["post"].permissions == ["iron-swarm.jobs.create"]
    assert contribution.endpoints[f"{base}/runs"]["get"].permissions == ["iron-swarm.runs.list"]
    assert contribution.endpoints[f"{base}/runs"]["get"].scopes == ["iron-swarm:read", "platform:read"]
    assert contribution.endpoints[f"{base}/runs/{{name}}/events"]["post"].permissions == [
        "iron-swarm.runs.events.write"
    ]
