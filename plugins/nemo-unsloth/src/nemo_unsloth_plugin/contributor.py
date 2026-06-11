# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth customization contributor.

Registered under ``nemo.customization.contributors`` (key ``unsloth``).
The customization router hub (``nemo-customizer-plugin``) discovers this
class at startup and:

- merges :meth:`get_routers` into ``/apis/customization/...``
- adds :meth:`get_cli` under ``nemo customization unsloth``
- merges :meth:`get_authz_contribution` into the platform authz policy
- composes :meth:`get_sdk_resources` under ``client.customization.unsloth``
"""

from __future__ import annotations

from typing import ClassVar

import typer
from fastapi import APIRouter
from nemo_platform_plugin.authz import AuthzContribution, authz_for_workspace_job_collection
from nemo_platform_plugin.customization_contributor import CustomizationContributorSDKResources
from nemo_platform_plugin.jobs.api_factory import JobRouteOption
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import RouterSpec

from nemo_unsloth_plugin.config import generate_unsloth_id, get_config
from nemo_unsloth_plugin.jobs.jobs import UnslothJob


class UnslothContributor:
    """Registers Unsloth routes/CLI under the customization router."""

    name: ClassVar[str] = "unsloth"
    # Remote container submit needs the same set of platform services as
    # automodel: workspace lookups, auth, jobs API, secrets passthrough,
    # files for the model + dataset filesets, and models for entity creation.
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]

    def get_routers(self) -> list[RouterSpec]:
        """Health endpoint + ``add_job_routes`` for the Unsloth job collection.

        Submit-only: a POST that reaches ``compile()`` builds a 4-step
        container job (download → train → upload → model-entity) the
        platform Jobs runner executes on the cluster.
        """
        config = get_config()
        router = APIRouter()

        @router.get("/healthz")
        async def healthz() -> dict[str, str]:
            return {"backend": self.name, "status": "ok"}

        jobs_router = add_job_routes(
            UnslothJob,
            service_name="customization",
            generate_job_name=generate_unsloth_id,
            route_options=[JobRouteOption.CORE],
            default_profile=config.default_training_execution_profile,
        )

        return [
            RouterSpec(
                router=router,
                prefix="/v2/workspaces/{workspace}/unsloth",
                tag="Unsloth",
                description="Unsloth contributor health.",
            ),
            RouterSpec(
                router=jobs_router,
                prefix="/v2/workspaces/{workspace}",
                tag="Unsloth Jobs",
                description="Unsloth GPU fine-tuning jobs (container submit).",
            ),
        ]

    def get_cli(self) -> typer.Typer:
        """Compose run/submit/explain verbs, then apply Unsloth-specific overrides.

        :func:`apply_unsloth_job_cli_overrides` reshapes ``submit`` to
        accept a positional ``JOB_JSON`` and hard-disables ``run`` (since
        Unsloth now runs remotely in a container, not locally).
        """
        from nemo_platform_plugin.commands import (
            _add_explain_command,
            _add_run_command,
            _add_submit_command,
        )
        from nemo_platform_plugin.scheduler import NemoJobScheduler

        from nemo_unsloth_plugin.cli.inputs import apply_unsloth_job_cli_overrides

        app = typer.Typer(
            name=self.name,
            help="Unsloth GPU fine-tuning (container submit). SFT only.",
            no_args_is_help=True,
        )
        scheduler = NemoJobScheduler()
        _add_run_command(app, UnslothJob, scheduler)
        _add_submit_command(app, UnslothJob, scheduler)
        _add_explain_command(app, UnslothJob, scheduler)
        apply_unsloth_job_cli_overrides(app)
        return app

    def get_authz_contribution(self) -> AuthzContribution:
        """Register Unsloth job routes with the platform authorization policy."""
        return authz_for_workspace_job_collection(
            api_area="customization",
            collection_suffix="/unsloth/jobs",
            permission_prefix="customization.unsloth.jobs",
            include_healthz=True,
            healthz_suffix="/unsloth/healthz",
        )

    def get_sdk_resources(self) -> CustomizationContributorSDKResources:
        from nemo_unsloth_plugin.sdk.resources import AsyncUnslothCustomization, UnslothCustomization

        return CustomizationContributorSDKResources(
            sync_resource=UnslothCustomization,
            async_resource=AsyncUnslothCustomization,
        )
