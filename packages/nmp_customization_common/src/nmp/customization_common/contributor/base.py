# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base customization contributor.

Both the unsloth and automodel contributors implement the same
``get_routers`` / ``get_cli`` / ``get_authz_contribution`` shape, differing only
in a handful of class-level values. This base collapses that; each backend's
``contributor.py`` keeps a small subclass at the entry-point path
(``nemo_<svc>_plugin.contributor:<Svc>Contributor``).
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar

import typer
from fastapi import APIRouter
from nemo_platform_plugin.authz import AuthzContribution, authz_for_workspace_job_collection
from nemo_platform_plugin.customization_contributor import CustomizationContributorSDKResources
from nemo_platform_plugin.jobs.api_factory import JobRouteOption
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import RouterSpec


class BaseContributor:
    """Registers a backend's routes/CLI/authz under the customization router."""

    #: Backend route segment / contributor key (e.g. ``"unsloth"``).
    name: ClassVar[str]
    #: The backend's ``NemoJob`` subclass.
    job_cls: ClassVar[type[Any]]
    #: ``nemo customization <name>`` Typer help text.
    cli_help: ClassVar[str]
    #: Description for the jobs ``RouterSpec``.
    jobs_router_description: ClassVar[str]
    #: Platform services the backend's container submit flow depends on.
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]

    @staticmethod
    def generate_job_name() -> str:
        """Generate a unique job name. Overridden per backend."""
        raise NotImplementedError

    def apply_cli_overrides(self, app: typer.Typer) -> None:
        """Apply backend-specific submit/run CLI overrides. Overridden per backend."""
        raise NotImplementedError

    @property
    def _title(self) -> str:
        return self.name.capitalize()

    def _get_config(self) -> Any:
        """Return the backend plugin config. Overridden per backend."""
        raise NotImplementedError

    def get_routers(self) -> list[RouterSpec]:
        """Health endpoint + ``add_job_routes`` for the backend job collection."""
        config = self._get_config()
        router = APIRouter()

        @router.get("/healthz")
        async def healthz() -> dict[str, str]:
            return {"backend": self.name, "status": "ok"}

        jobs_router = add_job_routes(
            self.job_cls,
            service_name="customization",
            generate_job_name=self.generate_job_name,
            route_options=[JobRouteOption.CORE],
            default_profile=config.default_training_execution_profile,
        )

        return [
            RouterSpec(
                router=router,
                prefix=f"/v2/workspaces/{{workspace}}/{self.name}",
                tag=self._title,
                description=f"{self._title} contributor health.",
            ),
            RouterSpec(
                router=jobs_router,
                prefix="/v2/workspaces/{workspace}",
                tag=f"{self._title} Jobs",
                description=self.jobs_router_description,
            ),
        ]

    def get_cli(self) -> typer.Typer:
        """Compose run/submit/explain verbs, then apply backend-specific overrides."""
        from nemo_platform_plugin.commands import (
            _add_explain_command,
            _add_run_command,
            _add_submit_command,
        )
        from nemo_platform_plugin.scheduler import NemoJobScheduler

        app = typer.Typer(name=self.name, help=self.cli_help, no_args_is_help=True)
        scheduler = NemoJobScheduler()
        _add_run_command(app, self.job_cls, scheduler)
        _add_submit_command(app, self.job_cls, scheduler)
        _add_explain_command(app, self.job_cls, scheduler)
        self.apply_cli_overrides(app)
        return app

    def get_authz_contribution(self) -> AuthzContribution:
        """Register the backend job routes with the platform authorization policy."""
        return authz_for_workspace_job_collection(
            api_area="customization",
            collection_suffix=f"/{self.name}/jobs",
            permission_prefix=f"customization.{self.name}.jobs",
            include_healthz=True,
            healthz_suffix=f"/{self.name}/healthz",
        )

    def get_sdk_resources(self) -> CustomizationContributorSDKResources | None:
        """Return SDK resource classes for ``client.customization.<name>``.

        Overridden per backend to supply the sync/async ``<Svc>Customization``
        classes (the customization hub composes them). Defaults to ``None`` for a
        backend with no Python SDK surface.
        """
        return None


# Re-exported so subclasses can annotate their override signatures if desired.
GenerateJobName = Callable[[], str]
