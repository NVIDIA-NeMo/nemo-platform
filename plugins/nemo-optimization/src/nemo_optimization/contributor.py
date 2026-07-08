# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customization contributor for the Tune (optimize) lane.

Mounts ``nemo customization optimize`` and the optimize job routes under the
Customizer hub (``/apis/customization``). Trial execution is delegated to the
Evaluator (``AgentEvaluator`` + ``FabricAgentRuntime``); this contributor owns
routing and the study job lifecycle only.
"""

from __future__ import annotations

from typing import ClassVar

import typer
from fastapi import APIRouter
from nemo_platform_plugin.authz import AuthzScope, CallerKind, path_rule
from nemo_platform_plugin.customization_contributor import CustomizationContributorSDKResources
from nemo_platform_plugin.jobs.api_factory import JobRouteOption
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import RouterSpec

from nemo_optimization.config import generate_optimize_id, get_config
from nemo_optimization.jobs.optimize import OptimizeJob


class OptimizationContributor:
    """Registers the Tune optimize lane under the customization router."""

    name: ClassVar[str] = "optimize"
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]

    def get_routers(self) -> list[RouterSpec]:
        config = get_config()
        router = APIRouter()

        @router.get("/healthz")
        @path_rule(callers=[CallerKind.PRINCIPAL], permissions=[])
        async def healthz() -> dict[str, str]:
            return {"backend": self.name, "status": "ok"}

        jobs_router = add_job_routes(
            OptimizeJob,
            service_name="customization",
            generate_job_name=generate_optimize_id,
            route_options=[JobRouteOption.CORE],
            default_profile=config.default_training_execution_profile,
            authz=AuthzScope("customization").child(self.name, "jobs"),
        )

        return [
            RouterSpec(
                router=router,
                prefix=f"/v2/workspaces/{{workspace}}/{self.name}",
                tag="Optimize",
                description="Optimize (Tune) contributor health.",
            ),
            RouterSpec(
                router=jobs_router,
                prefix="/v2/workspaces/{workspace}",
                tag="Optimize Jobs",
                description="Customizer Tune numeric-optimization study jobs.",
            ),
        ]

    def get_cli(self) -> typer.Typer:
        from nemo_platform_plugin.commands import (
            _add_explain_command,
            _add_run_command,
            _add_submit_command,
        )
        from nemo_platform_plugin.scheduler import NemoJobScheduler

        app = typer.Typer(
            name=self.name,
            help="Numeric hyperparameter optimization (Tune lane).",
            no_args_is_help=True,
        )
        scheduler = NemoJobScheduler()
        _add_run_command(app, OptimizeJob, scheduler)
        _add_submit_command(app, OptimizeJob, scheduler)
        _add_explain_command(app, OptimizeJob, scheduler)

        from nemo_optimization.cli_convert import convert_app

        app.add_typer(convert_app, name="convert")
        return app

    def get_sdk_resources(self) -> CustomizationContributorSDKResources | None:
        return None
