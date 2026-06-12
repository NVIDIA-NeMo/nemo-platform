# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agents plugin service — registers agent lifecycle management on the NeMo Platform."""

from __future__ import annotations

import logging
from typing import ClassVar

from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import NemoService, RouterSpec

logger = logging.getLogger(__name__)

# Permission namespace owned by this plugin. Every permission id (CRUD,
# gateway, and job-factory) starts with this prefix; ``api_area`` is the same
# string so route scopes resolve to ``agents:read`` / ``agents:write``.
_NAMESPACE = "agents"
_API_AREA = "agents"


# Permission sub-namespace per job collection, keyed by the job class. ``get_routers``
# passes each as ``permission_namespace`` to ``add_job_routes``, which stamps the
# collection's permissions onto the factory routes; the catalog is derived from there.
# The chosen sub-names are concise and stable, and need not match the job's URL path segment.
#   EvaluateAgentJob   /jobs/evaluate        -> agents.evaluate
#   EvaluateSuiteJob   /jobs/evaluate-suite  -> agents.suite
#   OptimizeSkillsJob  /jobs/optimize-skills -> agents.optimize-skills
#   AnalyzeBatchJob    /jobs/analyze         -> agents.analyze
#   OptimizeAgentJob   /jobs/optimize        -> agents.optimize
def _job_namespaces() -> dict[str, str]:
    from nemo_agents_plugin.jobs.analyze_batch import AnalyzeBatchJob
    from nemo_agents_plugin.jobs.evaluate_agent import EvaluateAgentJob
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteJob
    from nemo_agents_plugin.jobs.optimize_agent import OptimizeAgentJob
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob

    return {
        EvaluateAgentJob.__name__: f"{_NAMESPACE}.evaluate",
        EvaluateSuiteJob.__name__: f"{_NAMESPACE}.suite",
        OptimizeSkillsJob.__name__: f"{_NAMESPACE}.optimize-skills",
        AnalyzeBatchJob.__name__: f"{_NAMESPACE}.analyze",
        OptimizeAgentJob.__name__: f"{_NAMESPACE}.optimize",
    }


class AgentsService(NemoService):
    """Plugin service that contributes agent CRUD, deployment lifecycle, and gateway proxy routes.

    Registered under the ``nemo.services`` entry-point group.  The platform
    wraps this in a ``NemoServiceAdapter`` at startup and mounts all routes
    under ``/apis/agents``.

    The :class:`~nemo_agents_plugin.runner.controller.AgentDeploymentController`
    reconcile loop is registered separately under the ``nemo.controllers``
    entry-point group and managed by the platform runner — this service does
    not own the controller lifecycle.
    """

    name: ClassVar[str] = "agents"
    dependencies: ClassVar[list[str]] = ["entities", "auth", "secrets", "jobs", "files", "inference-gateway"]

    def get_routers(self) -> list[RouterSpec]:
        from nemo_agents_plugin.api.v2 import (
            agents,
            deployment_logs,
            deployments,
            gateway,
        )
        from nemo_agents_plugin.jobs.analyze_batch import AnalyzeBatchJob
        from nemo_agents_plugin.jobs.evaluate_agent import EvaluateAgentJob
        from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteJob
        from nemo_agents_plugin.jobs.optimize_agent import OptimizeAgentJob
        from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob

        ns = _job_namespaces()
        _prefix = "/v2/workspaces/{workspace}"
        return [
            RouterSpec(agents.router, tag="Agents", description="Agent CRUD", prefix=_prefix),
            RouterSpec(deployments.router, tag="Agent Deployments", description="Deployment lifecycle", prefix=_prefix),
            RouterSpec(
                deployment_logs.router,
                tag="Agent Deployments",
                description="Per-deployment log retrieval",
                prefix=_prefix,
            ),
            RouterSpec(
                gateway.router, tag="Agent Gateway", description="Proxy to running agent deployments", prefix=_prefix
            ),
            RouterSpec(
                add_job_routes(
                    EvaluateAgentJob,
                    permission_namespace=ns[EvaluateAgentJob.__name__],
                    api_area=_API_AREA,
                ),
                tag="Agents",
                description="Submit and track agent evaluation jobs",
                prefix=_prefix,
            ),
            # Distinct service_name per job type so each list endpoint filters
            # to rows of its own type only.  add_job_routes filters by
            # source=service_name; if all jobs shared the default service_name
            # ("nemo-agents-plugin"), listing /jobs/evaluate would pull in rows
            # from sibling types and 500 on Pydantic validation against the
            # wrong schema.
            RouterSpec(
                add_job_routes(
                    EvaluateSuiteJob,
                    service_name="nemo-agents-plugin-evaluate-suite",
                    permission_namespace=ns[EvaluateSuiteJob.__name__],
                    api_area=_API_AREA,
                ),
                tag="Agents",
                description="Submit and track evaluate-suite jobs (Harbor / NAT eval runner).",
                prefix=_prefix,
            ),
            RouterSpec(
                add_job_routes(
                    OptimizeSkillsJob,
                    service_name="nemo-agents-plugin-optimize-skills",
                    permission_namespace=ns[OptimizeSkillsJob.__name__],
                    api_area=_API_AREA,
                ),
                tag="Agents",
                description="Submit and track optimize-skills jobs (skills-improvement loop).",
                prefix=_prefix,
            ),
            RouterSpec(
                add_job_routes(
                    AnalyzeBatchJob,
                    service_name="nemo-agents-plugin-analyze",
                    permission_namespace=ns[AnalyzeBatchJob.__name__],
                    api_area=_API_AREA,
                ),
                tag="Agents",
                description="Submit and track analyze jobs (eval-suite batch analysis).",
                prefix=_prefix,
            ),
            RouterSpec(
                add_job_routes(
                    OptimizeAgentJob,
                    service_name="nemo-agents-plugin-optimize",
                    permission_namespace=ns[OptimizeAgentJob.__name__],
                    api_area=_API_AREA,
                ),
                tag="Agents",
                description="Submit and track optimize jobs (prompt tuning, HPO).",
                prefix=_prefix,
            ),
        ]
