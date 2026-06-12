# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agents plugin service — registers agent lifecycle management on the NeMo Platform."""

from __future__ import annotations

import logging
from typing import ClassVar

from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import NemoService, RouterSpec

logger = logging.getLogger(__name__)


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
                add_job_routes(EvaluateAgentJob),
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
                add_job_routes(EvaluateSuiteJob, service_name="nemo-agents-plugin-evaluate-suite"),
                tag="Agents",
                description="Submit and track evaluate-suite jobs (Harbor / NAT eval runner).",
                prefix=_prefix,
            ),
            RouterSpec(
                add_job_routes(OptimizeSkillsJob, service_name="nemo-agents-plugin-optimize-skills"),
                tag="Agents",
                description="Submit and track optimize-skills jobs (skills-improvement loop).",
                prefix=_prefix,
            ),
            RouterSpec(
                add_job_routes(AnalyzeBatchJob, service_name="nemo-agents-plugin-analyze"),
                tag="Agents",
                description="Submit and track analyze jobs (eval-suite batch analysis).",
                prefix=_prefix,
            ),
            RouterSpec(
                add_job_routes(OptimizeAgentJob, service_name="nemo-agents-plugin-optimize"),
                tag="Agents",
                description="Submit and track optimize jobs (prompt tuning, HPO).",
                prefix=_prefix,
            ),
        ]
