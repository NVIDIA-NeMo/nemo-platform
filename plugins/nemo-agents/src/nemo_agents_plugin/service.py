# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agents plugin service — registers agent lifecycle management on the NeMo Platform."""

from __future__ import annotations

import logging
from typing import ClassVar, NamedTuple

from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import NemoService, RouterSpec

logger = logging.getLogger(__name__)

# Permission namespace owned by this plugin. Every permission id (CRUD,
# gateway, and job-factory) starts with this prefix; ``api_area`` is the same
# string so route scopes resolve to ``agents:read`` / ``agents:write``.
_NAMESPACE = "agents"
_API_AREA = "agents"


class _JobCollection(NamedTuple):
    """One agents job collection — the single source of truth for both its permission
    sub-namespace and its mounted router, so the two can't drift. (Previously two hand-synced
    lists: a job added to ``get_routers`` but missed in the namespace map ``KeyError``ed the
    whole plugin at startup.)"""

    job_cls: type[NemoJob]
    subname: str  # permission sub-namespace suffix -> <_NAMESPACE>.<subname>.{create,...}
    service_name: str | None  # distinct jobs source (None ⇒ add_job_routes default)
    description: str


# Sub-names are concise and stable and need not match the job's URL path segment:
#   EvaluateAgentJob   /jobs/evaluate        -> agents.evaluate
#   EvaluateSuiteJob   /jobs/evaluate-suite  -> agents.suite
#   OptimizeSkillsJob  /jobs/optimize-skills -> agents.optimize-skills
#   AnalyzeBatchJob    /jobs/analyze         -> agents.analyze
#   OptimizeAgentJob   /jobs/optimize        -> agents.optimize
# Distinct service_name per job type so each list endpoint filters to rows of its own type only
# (add_job_routes filters source=service_name); sharing the default would let /jobs/<x> pull in
# sibling-type rows and 500 on the wrong schema.
def _job_collections() -> list[_JobCollection]:
    from nemo_agents_plugin.jobs.analyze_batch import AnalyzeBatchJob
    from nemo_agents_plugin.jobs.evaluate_agent import EvaluateAgentJob
    from nemo_agents_plugin.jobs.evaluate_suite import EvaluateSuiteJob
    from nemo_agents_plugin.jobs.optimize_agent import OptimizeAgentJob
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob

    return [
        _JobCollection(EvaluateAgentJob, "evaluate", None, "Submit and track agent evaluation jobs"),
        _JobCollection(
            EvaluateSuiteJob,
            "suite",
            "nemo-agents-plugin-evaluate-suite",
            "Submit and track evaluate-suite jobs (Harbor / NAT eval runner).",
        ),
        _JobCollection(
            OptimizeSkillsJob,
            "optimize-skills",
            "nemo-agents-plugin-optimize-skills",
            "Submit and track optimize-skills jobs (skills-improvement loop).",
        ),
        _JobCollection(
            AnalyzeBatchJob,
            "analyze",
            "nemo-agents-plugin-analyze",
            "Submit and track analyze jobs (eval-suite batch analysis).",
        ),
        _JobCollection(
            OptimizeAgentJob,
            "optimize",
            "nemo-agents-plugin-optimize",
            "Submit and track optimize jobs (prompt tuning, HPO).",
        ),
    ]


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

        _prefix = "/v2/workspaces/{workspace}"
        specs: list[RouterSpec] = [
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
        ]
        # Job-collection routers, derived from the single _job_collections() source so a new job
        # can't be wired here but missed in the permission map (or vice versa).
        for collection in _job_collections():
            specs.append(
                RouterSpec(
                    add_job_routes(
                        collection.job_cls,
                        service_name=collection.service_name,
                        permission_namespace=f"{_NAMESPACE}.{collection.subname}",
                        api_area=_API_AREA,
                    ),
                    tag="Agents",
                    description=collection.description,
                    prefix=_prefix,
                )
            )
        return specs
