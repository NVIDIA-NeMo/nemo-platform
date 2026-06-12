# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the agents plugin service wiring."""

from __future__ import annotations

from fastapi.routing import APIRoute
from nemo_agents_plugin.jobs.analyze_batch import AnalyzeBatchJob
from nemo_agents_plugin.jobs.evaluate_agent import EvaluateAgentJob
from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteJob
from nemo_agents_plugin.jobs.optimize_agent import OptimizeAgentJob
from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob
from nemo_agents_plugin.service import AgentsService
from nemo_platform_plugin.authz_format import validate_static_authz_data
from nemo_platform_plugin.authz_merge import merge_authz_contributions
from nemo_platform_plugin.scheduler import submit_path_for


def _mounted_routes() -> dict[str, set[str]]:
    service = AgentsService()
    routes: dict[str, set[str]] = {}
    for spec in service.get_routers():
        for route in spec.router.routes:
            if not isinstance(route, APIRoute):
                continue
            path = f"/apis/agents{spec.prefix}{route.path}".replace("{trailing_uri:path}", "{trailing_uri}")
            routes.setdefault(path, set()).update(route.methods)
    return routes


def _mounted_post_paths() -> set[str]:
    """All POST paths mounted by AgentsService, regardless of which router owns them.

    Avoids the description-string filter that earlier revisions used — copy-only
    docstring edits in service.py should not break route-shape tests.
    """
    return {path for path, methods in _mounted_routes().items() if "POST" in methods}


def test_authz_contribution_matches_mounted_routes() -> None:
    """Every agents API route should be registered with the PDP."""
    endpoints = AgentsService.get_authz_contribution().endpoints

    for path, methods in _mounted_routes().items():
        assert path in endpoints
        for method in methods:
            assert method.lower() in endpoints[path]


def test_authz_contribution_grants_studio_deployments_list_to_viewer() -> None:
    """Regression for 403 on GET /apis/agents/v2/workspaces/{workspace}/deployments."""
    contribution = AgentsService.get_authz_contribution()
    base_authz = {
        "authz": {
            "permissions": {},
            "roles": {
                "Viewer": {"permissions": []},
                "Editor": {"permissions": []},
            },
            "endpoints": {},
        }
    }

    merged = merge_authz_contributions(base_authz, [contribution.to_dict()])

    validate_static_authz_data(merged)
    viewer_permissions = merged["authz"]["roles"]["Viewer"]["permissions"]
    editor_permissions = merged["authz"]["roles"]["Editor"]["permissions"]
    endpoints = merged["authz"]["endpoints"]

    deployments_path = "/apis/agents/v2/workspaces/{workspace}/deployments"
    assert endpoints[deployments_path]["get"]["permissions"] == ["agents.deployments.list"]
    assert endpoints[deployments_path]["get"]["scopes"] == ["agents:read", "platform:read"]
    assert "agents.deployments.list" in viewer_permissions
    assert "agents.deployments.read" in viewer_permissions
    assert "agents.deployments.create" in editor_permissions
    assert "agents.gateway.exec" in viewer_permissions


def test_evaluate_job_route_matches_generated_submit_path() -> None:
    assert submit_path_for(EvaluateAgentJob, workspace="{workspace}") in _mounted_post_paths()


def test_evaluate_suite_job_route_matches_generated_submit_path() -> None:
    assert submit_path_for(EvaluateSuiteJob, workspace="{workspace}") in _mounted_post_paths()


def test_optimize_skills_job_route_matches_generated_submit_path() -> None:
    assert submit_path_for(OptimizeSkillsJob, workspace="{workspace}") in _mounted_post_paths()


def test_analyze_job_route_matches_generated_submit_path() -> None:
    assert submit_path_for(AnalyzeBatchJob, workspace="{workspace}") in _mounted_post_paths()


def test_optimize_job_route_matches_generated_submit_path() -> None:
    assert submit_path_for(OptimizeAgentJob, workspace="{workspace}") in _mounted_post_paths()
