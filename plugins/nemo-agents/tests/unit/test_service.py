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
from nemo_platform_plugin.scheduler import submit_path_for


def _mounted_post_paths_for(description: str) -> set[str]:
    service = AgentsService()
    router_spec = next(spec for spec in service.get_routers() if spec.description == description)
    return {
        f"/apis/agents{router_spec.prefix}{route.path}"
        for route in router_spec.router.routes
        if isinstance(route, APIRoute) and "POST" in route.methods
    }


def test_evaluate_job_route_matches_generated_submit_path() -> None:
    mounted = _mounted_post_paths_for("Submit and track agent evaluation jobs")
    assert submit_path_for(EvaluateAgentJob, workspace="{workspace}") in mounted


def test_evaluate_suite_job_route_matches_generated_submit_path() -> None:
    mounted = _mounted_post_paths_for("Submit and track evaluate-suite jobs (Harbor / NAT eval runner).")
    assert submit_path_for(EvaluateSuiteJob, workspace="{workspace}") in mounted


def test_optimize_skills_job_route_matches_generated_submit_path() -> None:
    mounted = _mounted_post_paths_for("Submit and track optimize-skills jobs (skills-improvement loop).")
    assert submit_path_for(OptimizeSkillsJob, workspace="{workspace}") in mounted


def test_analyze_job_route_matches_generated_submit_path() -> None:
    mounted = _mounted_post_paths_for("Submit and track analyze jobs (eval-suite batch analysis).")
    assert submit_path_for(AnalyzeBatchJob, workspace="{workspace}") in mounted


def test_optimize_job_route_matches_generated_submit_path() -> None:
    mounted = _mounted_post_paths_for("Submit and track optimize jobs (prompt tuning, HPO).")
    assert submit_path_for(OptimizeAgentJob, workspace="{workspace}") in mounted
