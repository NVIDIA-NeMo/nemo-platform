# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel training job (NemoJob).

Shared scaffold (``to_spec`` + the Docker-runtime guard) lives in
:class:`nmp.customization_common.contributor.jobs.BaseSubmitJob`; ``compile`` stays here
because it validates for training and resolves the execution profile from the
schema (automodel-specific).
"""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_automodel_plugin.config import get_config
from nemo_automodel_plugin.schema import AutomodelJobInput, AutomodelJobOutput
from nemo_automodel_plugin.transform import transform_input_to_output
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.docker import validate_gpu_available_for_docker
from nmp.automodel.compile import platform_job_config_compiler
from nmp.customization_common.contributor.jobs import BaseSubmitJob, require_docker_runtime
from pydantic import BaseModel


class AutomodelJob(BaseSubmitJob):
    """GPU Automodel fine-tuning job under the customization router."""

    name: ClassVar[str] = "automodel.jobs"
    description: ClassVar[str] = "Automodel SFT and knowledge-distillation training jobs."
    job_collection_path: ClassVar[str | None] = "/automodel/jobs"
    input_spec_schema: ClassVar[type[BaseModel] | None] = AutomodelJobInput
    spec_schema: ClassVar[type[BaseModel] | None] = AutomodelJobOutput
    docker_runtime_label: ClassVar[str] = "Automodel"

    @classmethod
    async def _transform(cls, job_input: BaseModel, workspace: str, async_sdk: AsyncNeMoPlatform) -> AutomodelJobOutput:
        return await transform_input_to_output(cast(AutomodelJobInput, job_input), workspace, async_sdk)

    @classmethod
    async def compile(
        cls,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        del entity_client, options
        require_docker_runtime(cls.docker_runtime_label)
        canonical = (
            spec if isinstance(spec, AutomodelJobOutput) else AutomodelJobOutput.model_validate(spec.model_dump())
        )
        canonical.validate_for_training()

        plugin_config = get_config()
        execution_profile = (
            canonical.training.execution_profile or profile or plugin_config.default_training_execution_profile
        )

        platform_spec = await platform_job_config_compiler(
            canonical,
            workspace,
            cast(AsyncNeMoPlatform, async_sdk),
            job_name=job_name,
            profile=execution_profile,
        )

        validate_gpu_available_for_docker(platform_spec)
        return platform_spec
