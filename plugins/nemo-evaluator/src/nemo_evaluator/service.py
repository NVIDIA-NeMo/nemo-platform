# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service surface for the evaluator plugin scaffold."""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter
from nemo_evaluator.core import say_hello
from nemo_evaluator.jobs.evaluate import EvaluateJob
from nemo_evaluator.schema import HelloResponse
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import NemoService, RouterSpec


class EvaluatorPluginService(NemoService):
    """Minimal service surface for evaluator pluginification work."""

    name: ClassVar[str] = "evaluator"
    dependencies: ClassVar[list[str]] = ["nemo-evaluator-sdk"]

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
        ]


def _build_hello_router() -> APIRouter:
    router = APIRouter()

    @router.get("/hello/{name}", response_model=HelloResponse)
    async def hello(name: str) -> HelloResponse:
        """Greet a name."""
        return HelloResponse(message=say_hello(name))

    return router
