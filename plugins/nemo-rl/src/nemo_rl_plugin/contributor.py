# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo-RL customization contributor.

Registered under ``nemo.customization.contributors`` (key ``rl``). The
customization router hub (``nemo-customizer-plugin``) discovers this class and
merges its routes/CLI/authz/SDK. Shared shape lives in
:class:`nmp.customization_common.contributor.base.BaseContributor`.
"""

from __future__ import annotations

from typing import ClassVar

import typer
from nemo_platform_plugin.customization_contributor import CustomizationContributorSDKResources
from nmp.customization_common.contributor.base import BaseContributor

from nemo_rl_plugin.config import RlPluginConfig, generate_rl_id, get_config
from nemo_rl_plugin.jobs.jobs import RlJob


class RlContributor(BaseContributor):
    """Registers NeMo-RL routes/CLI under the customization router (DPO, Kubernetes only)."""

    name: ClassVar[str] = "rl"
    job_cls: ClassVar[type] = RlJob
    cli_help: ClassVar[str] = "NeMo-RL preference training (DPO) on a Ray cluster. Remote Kubernetes only."
    jobs_router_description: ClassVar[str] = "NeMo-RL DPO training jobs (Ray on Kubernetes)."

    generate_job_name = staticmethod(generate_rl_id)

    def _get_config(self) -> RlPluginConfig:
        return get_config()

    def apply_cli_overrides(self, app: typer.Typer) -> None:
        from nemo_rl_plugin.cli.inputs import apply_rl_job_cli_overrides

        apply_rl_job_cli_overrides(app)

    def get_sdk_resources(self) -> CustomizationContributorSDKResources:
        from nemo_rl_plugin.sdk.resources import AsyncRlCustomization, RlCustomization

        return CustomizationContributorSDKResources(
            sync_resource=RlCustomization,
            async_resource=AsyncRlCustomization,
        )
