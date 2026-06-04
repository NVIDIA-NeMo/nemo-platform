# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Factory for customization contributor classes (routes, CLI, authz)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import typer
from fastapi import APIRouter
from nemo_platform_plugin.authz import AuthzContribution, authz_for_workspace_job_collection
from nemo_platform_plugin.jobs.api_factory import JobRouteOption
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.service import RouterSpec


@dataclass(frozen=True)
class ContributorBackendConfig:
    """Static configuration for a GPU customization backend contributor."""

    name: str
    tag: str
    cli_help: str
    health_description: str
    jobs_description: str
    job_cls: type
    generate_job_name: Callable[[], str]
    get_config: Callable[[], object]
    apply_cli_overrides: Callable[[typer.Typer], None]


_PLATFORM_DEPENDENCIES: tuple[str, ...] = (
    "entities",
    "auth",
    "jobs",
    "secrets",
    "files",
    "models",
)


def make_customization_contributor(
    config: ContributorBackendConfig,
    class_name: str | None = None,
) -> type:
    """Build a contributor class registered under ``nemo.customization.contributors``.

    Args:
        config: Backend-specific job class, ID generator, and CLI hooks.
        class_name: Optional explicit class name (e.g. ``UnslothContributor``).
    """
    resolved_name = class_name or f"{config.name.title()}Contributor"

    class _Contributor:
        """Registers customization routes/CLI under the customization router."""

        name: ClassVar[str] = config.name
        dependencies: ClassVar[list[str]] = list(_PLATFORM_DEPENDENCIES)

        def get_routers(self) -> list[RouterSpec]:
            plugin_config = config.get_config()
            router = APIRouter()

            @router.get("/healthz")
            async def healthz() -> dict[str, str]:
                return {"backend": self.name, "status": "ok"}

            jobs_router = add_job_routes(
                config.job_cls,
                service_name="customization",
                generate_job_name=config.generate_job_name,
                route_options=[JobRouteOption.CORE],
                default_profile=plugin_config.default_training_execution_profile,
            )

            return [
                RouterSpec(
                    router=router,
                    prefix=f"/v2/workspaces/{{workspace}}/{config.name}",
                    tag=config.tag,
                    description=config.health_description,
                ),
                RouterSpec(
                    router=jobs_router,
                    prefix="/v2/workspaces/{workspace}",
                    tag=f"{config.tag} Jobs",
                    description=config.jobs_description,
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
                help=config.cli_help,
                no_args_is_help=True,
            )
            scheduler = NemoJobScheduler()
            _add_run_command(app, config.job_cls, scheduler)
            _add_submit_command(app, config.job_cls, scheduler)
            _add_explain_command(app, config.job_cls, scheduler)
            config.apply_cli_overrides(app)
            return app

        def get_authz_contribution(self) -> AuthzContribution:
            return authz_for_workspace_job_collection(
                api_area="customization",
                collection_suffix=f"/{config.name}/jobs",
                permission_prefix=f"customization.{config.name}.jobs",
                include_healthz=True,
                healthz_suffix=f"/{config.name}/healthz",
            )

    _Contributor.__name__ = resolved_name
    _Contributor.__qualname__ = resolved_name
    _Contributor.__doc__ = f"Registers {config.tag} routes/CLI under the customization router."
    return _Contributor
