# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel customization contributor."""

from __future__ import annotations

from typing import ClassVar

import typer
from fastapi import APIRouter
from nemo_platform_plugin.authz import AuthzContribution, authz_for_workspace_job_collection
from nemo_platform_plugin.customization_contributor import CustomizationContributorSDKResources
from nemo_platform_plugin.jobs.api_factory import JobRouteOption
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import RouterSpec

from nemo_automodel_plugin.config import generate_automodel_id, get_config
from nemo_automodel_plugin.jobs.jobs import AutomodelJob


class AutomodelContributor:
    """Registers Automodel routes under the customization router."""

    name: ClassVar[str] = "automodel"
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]

    def get_routers(self) -> list[RouterSpec]:
        config = get_config()
        router = APIRouter()

        @router.get("/healthz")
        async def healthz() -> dict[str, str]:
            return {"backend": self.name, "status": "ok"}

        jobs_router = add_job_routes(
            AutomodelJob,
            service_name="customization",
            generate_job_name=generate_automodel_id,
            route_options=[JobRouteOption.CORE],
            default_profile=config.default_training_execution_profile,
        )

        return [
            RouterSpec(
                router=router,
                prefix="/v2/workspaces/{workspace}/automodel",
                tag="Automodel",
                description="Automodel contributor health.",
            ),
            RouterSpec(
                router=jobs_router,
                prefix="/v2/workspaces/{workspace}",
                tag="Automodel Jobs",
                description="Automodel training jobs.",
            ),
        ]

    def get_cli(self) -> typer.Typer:
        from nemo_platform_plugin.commands import (
            _add_explain_command,
            _add_run_command,
            _add_submit_command,
        )
        from nemo_platform_plugin.scheduler import NemoJobScheduler

        from nemo_automodel_plugin.cli.inputs import apply_automodel_job_cli_overrides

        app = typer.Typer(
            name=self.name,
            help="Automodel training jobs (SFT, distillation).",
            no_args_is_help=True,
        )
        scheduler = NemoJobScheduler()
        _add_run_command(app, AutomodelJob, scheduler)
        _add_submit_command(app, AutomodelJob, scheduler)
        _add_explain_command(app, AutomodelJob, scheduler)
        apply_automodel_job_cli_overrides(app)
        return app

    def get_authz_contribution(self) -> AuthzContribution:
        """Register automodel job routes with the platform authorization policy."""
        return authz_for_workspace_job_collection(
            api_area="customization",
            collection_suffix="/automodel/jobs",
            permission_prefix="customization.automodel.jobs",
            include_healthz=True,
            healthz_suffix="/automodel/healthz",
        )

    def get_sdk_resources(self) -> CustomizationContributorSDKResources:
        from nemo_automodel_plugin.sdk.resources import AsyncAutomodelCustomization, AutomodelCustomization

        return CustomizationContributorSDKResources(
            sync_resource=AutomodelCustomization,
            async_resource=AsyncAutomodelCustomization,
        )
