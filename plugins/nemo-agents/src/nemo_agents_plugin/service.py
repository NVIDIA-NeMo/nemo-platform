# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agents plugin service — registers agent lifecycle management on the NeMo Platform."""

from __future__ import annotations

import logging
from typing import ClassVar

from nemo_platform_plugin.authz import AuthzContribution, AuthzEndpointMethod
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import NemoService, RouterSpec

logger = logging.getLogger(__name__)

_SERVICE_NAME = "agents"
_READ_SCOPES = [f"{_SERVICE_NAME}:read", "platform:read"]
_WRITE_SCOPES = [f"{_SERVICE_NAME}:write", "platform:write"]


def _read_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_READ_SCOPES))


def _write_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_WRITE_SCOPES))


def _gateway_methods(permission: str) -> dict[str, AuthzEndpointMethod]:
    read_methods = {"get", "head", "options"}
    return {
        method: _read_method(permission) if method in read_methods else _write_method(permission)
        for method in ("delete", "get", "head", "options", "patch", "post", "put")
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

    name: ClassVar[str] = _SERVICE_NAME
    dependencies: ClassVar[list[str]] = ["entities", "auth", "secrets", "jobs", "files", "inference-gateway"]

    @classmethod
    def get_authz_contribution(cls) -> AuthzContribution:
        """Authorization policy for agents plugin routes."""
        base = f"/apis/{cls.name}/v2/workspaces/{{workspace}}"

        agent_create = f"{cls.name}.agents.create"
        agent_delete = f"{cls.name}.agents.delete"
        agent_list = f"{cls.name}.agents.list"
        agent_read = f"{cls.name}.agents.read"
        deployment_create = f"{cls.name}.deployments.create"
        deployment_delete = f"{cls.name}.deployments.delete"
        deployment_list = f"{cls.name}.deployments.list"
        deployment_read = f"{cls.name}.deployments.read"
        gateway_exec = f"{cls.name}.gateway.exec"
        job_cancel = f"{cls.name}.jobs.cancel"
        job_create = f"{cls.name}.jobs.create"
        job_delete = f"{cls.name}.jobs.delete"
        job_list = f"{cls.name}.jobs.list"
        job_read = f"{cls.name}.jobs.read"

        endpoints: dict[str, dict[str, AuthzEndpointMethod]] = {
            f"{base}/agents": {
                "get": _read_method(agent_list),
                "post": _write_method(agent_create),
            },
            f"{base}/agents/{{name}}": {
                "delete": _write_method(agent_delete),
                "get": _read_method(agent_read),
            },
            f"{base}/agents/{{name}}/-/{{trailing_uri}}": _gateway_methods(gateway_exec),
            f"{base}/deployments": {
                "get": _read_method(deployment_list),
                "post": _write_method(deployment_create),
            },
            f"{base}/deployments/{{name}}": {
                "delete": _write_method(deployment_delete),
                "get": _read_method(deployment_read),
            },
            f"{base}/deployments/{{name}}/-/{{trailing_uri}}": _gateway_methods(gateway_exec),
            f"{base}/deployments/{{name}}/logs": {
                "get": _read_method(deployment_read),
            },
            f"{base}/deployments/{{name}}/logs/stream": {
                "get": _read_method(deployment_read),
            },
        }

        for job_name in ("evaluate", "evaluate-suite", "optimize-skills", "analyze", "optimize"):
            jobs_base = f"{base}/jobs/{job_name}"
            endpoints.update(
                {
                    jobs_base: {
                        "get": _read_method(job_list),
                        "post": _write_method(job_create),
                    },
                    f"{jobs_base}/{{name}}": {
                        "delete": _write_method(job_delete),
                        "get": _read_method(job_read),
                    },
                    f"{jobs_base}/{{name}}/cancel": {
                        "post": _write_method(job_cancel),
                    },
                    f"{jobs_base}/{{name}}/logs": {
                        "get": _read_method(job_read),
                    },
                    f"{jobs_base}/{{name}}/results": {
                        "get": _read_method(job_read),
                    },
                    f"{jobs_base}/{{name}}/status": {
                        "get": _read_method(job_read),
                    },
                    f"{jobs_base}/{{job}}/results/{{name}}": {
                        "get": _read_method(job_read),
                    },
                    f"{jobs_base}/{{job}}/results/{{name}}/download": {
                        "get": _read_method(job_read),
                    },
                }
            )

        return AuthzContribution(
            permissions={
                agent_create: "Create agents",
                agent_delete: "Delete agents",
                agent_list: "List agents",
                agent_read: "Read agents",
                deployment_create: "Create agent deployments",
                deployment_delete: "Delete agent deployments",
                deployment_list: "List agent deployments",
                deployment_read: "Read agent deployments",
                gateway_exec: "Execute agent gateway requests",
                job_cancel: "Cancel agent jobs",
                job_create: "Create agent jobs",
                job_delete: "Delete agent jobs",
                job_list: "List agent jobs",
                job_read: "Read agent jobs",
            },
            endpoints=endpoints,
            role_permissions={
                "Viewer": [gateway_exec],
                "Editor": [gateway_exec],
            },
        )

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
