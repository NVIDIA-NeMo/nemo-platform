# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service surface for the evaluator plugin scaffold."""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter
from nemo_evaluator.api.v2 import metrics as metrics_routes
from nemo_evaluator.core import say_hello
from nemo_evaluator.jobs.evaluate import EvaluateJob
from nemo_evaluator.schema import HelloResponse
from nemo_platform_plugin.authz import (
    AuthzContribution,
    AuthzEndpointMethod,
    authz_for_workspace_job_collection,
    combine_authz_contributions,
)
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import NemoService, RouterSpec


def _authz_for_metrics_collection(api_area: str, permission_prefix: str) -> AuthzContribution:
    """Authz for the stored-metrics CRUD collection (full path includes PUT)."""
    base = f"/apis/{api_area}/v2/workspaces/{{workspace}}/metrics"
    read_scopes = [f"{api_area}:read", "platform:read"]
    write_scopes = [f"{api_area}:write", "platform:write"]
    return AuthzContribution(
        permissions={
            f"{permission_prefix}.create": f"Create {permission_prefix}",
            f"{permission_prefix}.list": f"List {permission_prefix}",
            f"{permission_prefix}.read": f"Read {permission_prefix}",
            f"{permission_prefix}.delete": f"Delete {permission_prefix}",
        },
        endpoints={
            base: {
                "get": AuthzEndpointMethod(permissions=[f"{permission_prefix}.list"], scopes=read_scopes),
            },
            f"{base}/{{name}}": {
                "post": AuthzEndpointMethod(permissions=[f"{permission_prefix}.create"], scopes=write_scopes),
                "get": AuthzEndpointMethod(permissions=[f"{permission_prefix}.read"], scopes=read_scopes),
                "delete": AuthzEndpointMethod(permissions=[f"{permission_prefix}.delete"], scopes=write_scopes),
            },
        },
    )


class EvaluatorPluginService(NemoService):
    """Minimal service surface for evaluator pluginification work."""

    name: ClassVar[str] = "evaluator"
    dependencies: ClassVar[list[str]] = ["nemo-evaluator-sdk", "entities", "files"]

    @classmethod
    def get_authz_contribution(cls) -> AuthzContribution:
        return combine_authz_contributions(
            AuthzContribution(
                endpoints={
                    f"/apis/{cls.name}/v1/healthz": {
                        "get": AuthzEndpointMethod(permissions=[], scopes=[]),
                    },
                    f"/apis/{cls.name}/v1/hello/{{name}}": {
                        "get": AuthzEndpointMethod(permissions=[], scopes=[]),
                    },
                },
            ),
            authz_for_workspace_job_collection(
                api_area=cls.name,
                collection_suffix="/evaluate/jobs",
                permission_prefix=f"{cls.name}.jobs",
            ),
            _authz_for_metrics_collection(
                api_area=cls.name,
                permission_prefix=f"{cls.name}.metrics",
            ),
        )

    def get_routers(self) -> list[RouterSpec]:
        router = APIRouter()
        jobs_router = add_job_routes(EvaluateJob)

        @router.get("/healthz")
        async def healthz() -> dict[str, object]:
            return {
                "plugin": self.name,
                "status": "ok",
                "mode": "sdk-backed-job-scaffold",
                "jobs": ["evaluator.evaluate"],
            }

        return [
            RouterSpec(
                router=router,
                tag="Evaluator Plugin",
                description="Evaluator plugin scaffold routes.",
                prefix="/v1",
            ),
            RouterSpec(
                # curl localhost:8080/apis/evaluator/v1/hello/friend
                router=_build_hello_router(),
                tag="Evaluator Plugin Hello Routes",
                description="Evaluator hello endpoint.",
                prefix="/v1",
            ),
            RouterSpec(
                # POST /apis/evaluator/v2/workspaces/{workspace}/evaluate/jobs.
                router=jobs_router,
                tag="Evaluator Plugin Jobs Routes",
                description="Evaluator plugin jobs routes.",
                prefix="/v2/workspaces/{workspace}",
            ),
            RouterSpec(
                # CRUD /apis/evaluator/v2/workspaces/{workspace}/metrics.
                router=metrics_routes.router,
                tag="Evaluator Plugin Metrics Routes",
                description="Stored metric (metric bundle) CRUD routes.",
                prefix="/v2/workspaces/{workspace}",
            ),
        ]


def _build_hello_router() -> APIRouter:
    router = APIRouter()

    @router.get("/hello/{name}", response_model=HelloResponse)
    async def hello(name: str) -> HelloResponse:
        """Greet a name."""
        return HelloResponse(message=say_hello(name))

    return router
