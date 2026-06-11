# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel training job (NemoJob)."""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.config import NemoPlatformConfig, Runtime
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.docker import validate_gpu_available_for_docker
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nmp.automodel.compile import platform_job_config_compiler
from pydantic import BaseModel

from nemo_automodel_plugin.config import get_config
from nemo_automodel_plugin.schema import AutomodelJobInput, AutomodelJobOutput
from nemo_automodel_plugin.transform import transform_input_to_output


def _require_docker_runtime() -> None:
    platform_config = NemoPlatformConfig.get()
    if platform_config.runtime != Runtime.DOCKER:
        raise PlatformJobCompilationError(
            "Automodel training requires platform.runtime: docker with GPU-backed container execution.",
        )
    from nemo_platform_plugin.config import validate_docker_available

    if not validate_docker_available():
        raise PlatformJobCompilationError(
            "Automodel training requires a reachable Docker daemon (platform.runtime: docker).",
        )


class AutomodelJob(NemoJob):
    """GPU Automodel fine-tuning job under the customization router."""

    name: ClassVar[str] = "automodel.jobs"
    description: ClassVar[str] = "Automodel SFT and knowledge-distillation training jobs."
    job_collection_path: ClassVar[str | None] = "/automodel/jobs"
    input_spec_schema: ClassVar[type[BaseModel] | None] = AutomodelJobInput
    spec_schema: ClassVar[type[BaseModel] | None] = AutomodelJobOutput
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> AutomodelJobOutput:
        job_input = (
            input_spec
            if isinstance(input_spec, AutomodelJobInput)
            else AutomodelJobInput.model_validate(input_spec.model_dump())
        )
        return await transform_input_to_output(job_input, workspace, cast(AsyncNeMoPlatform, async_sdk))

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
        _require_docker_runtime()
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
