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


def _mounted_post_paths() -> set[str]:
    """All POST paths mounted by AgentsService, regardless of which router owns them.

    Avoids the description-string filter that earlier revisions used — copy-only
    docstring edits in service.py should not break route-shape tests.
    """
    service = AgentsService()
    return {
        f"/apis/agents{spec.prefix}{route.path}"
        for spec in service.get_routers()
        for route in spec.router.routes
        if isinstance(route, APIRoute) and "POST" in route.methods
    }


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
