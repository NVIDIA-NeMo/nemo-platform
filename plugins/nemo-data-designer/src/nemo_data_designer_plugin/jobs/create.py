# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data Designer create job."""

from __future__ import annotations

from typing import ClassVar, cast

import data_designer.config as dd
from data_designer_nemo.context import DataDesignerContext, create_data_designer_context
from data_designer_nemo.errors import NDDError, NDDInternalError, NDDInvalidConfigError
from data_designer_nemo.model_configs import get_model_configs
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
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
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

        # Aggregate errors across context validation and model config/provider
        # resolution. ``errors`` is the per-call buffer; once we've run every
        # check we either raise (with all errors aggregated) or proceed with
        # the resolved values.
        errors: list[NDDError] = []
        model_configs, model_providers = await _get_model_configs_and_providers(dd_ctx, input_spec.config, errors)
        errors.extend(await dd_ctx.validate(input_spec.config))
        _raise_if_errors(errors)

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


async def _get_model_configs_and_providers(
    dd_ctx: DataDesignerContext,
    config: dd.DataDesignerConfig,
    errors: list[NDDError],
) -> tuple[list[dd.ModelConfig], list[dd.ModelProvider]]:
    """Resolve referenced model configs / providers, appending failures to ``errors``."""
    model_configs: list[dd.ModelConfig] = []
    model_providers: list[dd.ModelProvider] = []

    try:
        model_configs = get_model_configs(config)
    except NDDInvalidConfigError as e:
        errors.append(e)
    else:
        try:
            model_providers = await dd_ctx.get_model_providers(model_configs)
        except (NDDInvalidConfigError, NDDInternalError) as e:
            errors.append(e)

    return model_configs, model_providers


def _raise_if_errors(errors: list[NDDError]) -> None:
    """Raise an aggregated error if ``errors`` is non-empty.

    Any config-level error wins (422 path) and surfaces as
    :class:`PlatformJobCompilationError`, which the job-route handler maps to
    HTTP 422. Only when *every* error is internal do we raise
    :class:`NDDInternalError` (500 path).
    """
    if not errors:
        return
    aggregated_message = "\n".join(str(e) for e in errors)
    # TODO: raise a more generic error (not "job compilation")
    if any(isinstance(e, NDDInvalidConfigError) for e in errors):
        raise PlatformJobCompilationError(aggregated_message)
    raise NDDInternalError(aggregated_message)
