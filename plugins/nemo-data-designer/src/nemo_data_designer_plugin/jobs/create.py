# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data Designer create job."""

from __future__ import annotations

from typing import ClassVar, cast

from data_designer_nemo.context import create_data_designer_context
from data_designer_nemo.errors import raise_if_errors
from data_designer_nemo.runnable import resolve_runnable_config
from nemo_data_designer_plugin.jobs.run import run_step_config_result
from nemo_data_designer_plugin.jobs.spec import DataDesignerJobConfig, DataDesignerStepConfig
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nmp.common.jobs.image import get_qualified_image
from pydantic import BaseModel


class CreateJob(NemoJob):
    name: ClassVar[str] = "create"
    description: ClassVar[str] = "Generate a synthetic dataset"
    container: ClassVar[str] = "cpu-tasks"

    input_spec_schema = DataDesignerJobConfig
    spec_schema = DataDesignerStepConfig

    # TODO: Use stronger types once available (also in `compile`)
    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,  # DataDesignerJobConfig
        *,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> BaseModel:  # DataDesignerStepConfig
        async_sdk = cast(AsyncNeMoPlatform, async_sdk)
        input_spec = cast(DataDesignerJobConfig, input_spec)

        dd_ctx = create_data_designer_context(is_local, async_sdk, workspace)
        errors, model_configs, model_providers = await resolve_runnable_config(dd_ctx, input_spec.config)
        raise_if_errors(errors)

        return DataDesignerStepConfig(
            job_config=input_spec,
            model_providers=model_providers,
            model_configs=model_configs,
        )

    @classmethod
    async def compile(
        cls,
        *,
        workspace: str,
        spec: BaseModel,  # DataDesignerStepConfig
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="data-designer-job",
                    executor=CPUExecutionProviderSpec(
                        profile=profile or "default",
                        provider="cpu",
                        container=ContainerSpec(
                            image=get_qualified_image("nmp-cpu-tasks"),
                            entrypoint=["python", "-m"],
                            command=["nemo_data_designer_plugin.jobs.bridge"],
                        ),
                    ),
                    config=spec.model_dump(),
                    environment=[],
                )
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform, is_local: bool = False) -> dict:
        step_config = DataDesignerStepConfig.model_validate(config)
        return run_step_config_result(step_config, ctx, sdk, is_local)
