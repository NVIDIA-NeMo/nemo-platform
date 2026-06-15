# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth remote-submit training job (NemoJob).

Submit-only — Unsloth executes as a 4-step ``PlatformJobSpec`` (download
→ train → upload → model-entity) on the platform's GPU cluster.

Shared scaffold (``to_spec`` + the Docker-runtime guard) lives in
:class:`nmp.customization_common.contributor.jobs.BaseSubmitJob`; ``compile`` stays here
because the compiler call convention and profile resolution are backend-specific.
"""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.docker import validate_gpu_available_for_docker
from nemo_unsloth_plugin.schema import UnslothJobInput
from nemo_unsloth_plugin.transform import transform_input_to_output
from nmp.customization_common.contributor.jobs import BaseSubmitJob, require_docker_runtime
from nmp.unsloth.compile import platform_job_config_compiler
from nmp.unsloth.config import config as unsloth_config
from nmp.unsloth.schemas import UnslothJobOutput
from pydantic import BaseModel


class UnslothJob(BaseSubmitJob):
    """GPU Unsloth fine-tuning job under the customization router (submit-only)."""

    name: ClassVar[str] = "unsloth.jobs"
    description: ClassVar[str] = "Unsloth SFT (LoRA / full / merged) training jobs on the platform GPU cluster."
    job_collection_path: ClassVar[str | None] = "/unsloth/jobs"
    input_spec_schema: ClassVar[type[BaseModel] | None] = UnslothJobInput
    spec_schema: ClassVar[type[BaseModel] | None] = UnslothJobOutput
    docker_runtime_label: ClassVar[str] = "Unsloth"

    @classmethod
    async def _transform(cls, job_input: BaseModel, workspace: str, async_sdk: AsyncNeMoPlatform) -> UnslothJobOutput:
        return await transform_input_to_output(cast(UnslothJobInput, job_input), workspace, async_sdk)

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
        """Compile a validated :class:`UnslothJobOutput` into a 4-step container job.

        Unsloth's :class:`HardwareSpec` does not expose an ``execution_profile``
        field, so resolution is ``profile`` arg →
        ``unsloth_config.default_training_execution_profile``.
        """
        del entity_client, options
        require_docker_runtime(cls.docker_runtime_label)
        canonical = spec if isinstance(spec, UnslothJobOutput) else UnslothJobOutput.model_validate(spec.model_dump())

        execution_profile = profile or unsloth_config.default_training_execution_profile

        platform_spec = await platform_job_config_compiler(
            workspace=workspace,
            spec=canonical,
            sdk=cast(AsyncNeMoPlatform, async_sdk),
            job_name=job_name,
            profile=execution_profile,
        )

        validate_gpu_available_for_docker(platform_spec)
        return platform_spec
