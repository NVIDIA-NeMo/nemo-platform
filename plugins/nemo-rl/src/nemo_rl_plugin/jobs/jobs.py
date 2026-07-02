# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo-RL remote-submit DPO training job (NemoJob).

Submit-only — executes as a 4-step ``PlatformJobSpec`` (download → DPO train →
upload → model-entity) on the platform's Kubernetes GPU cluster, where the
training step provisions a Ray cluster.

Shared scaffold (``to_spec``) lives in
:class:`nmp.customization_common.contributor.jobs.BaseSubmitJob`. ``compile``
stays here: it gates on the Kubernetes runtime (no local Docker fallback) and
resolves the execution profile.
"""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_rl_plugin.schema import RlJobInput
from nemo_rl_plugin.transform import transform_input_to_output
from nmp.customization_common.contributor.jobs import BaseSubmitJob, require_distributed_runtime
from nmp.rl.compile import platform_job_config_compiler
from nmp.rl.schemas import RlJobOutput
from pydantic import BaseModel


class RlJob(BaseSubmitJob):
    """NeMo-RL DPO training job under the customization router (submit-only)."""

    name: ClassVar[str] = "rl.jobs"
    description: ClassVar[str] = "NeMo-RL DPO training jobs on the platform Kubernetes GPU cluster (Ray)."
    job_collection_path: ClassVar[str | None] = "/rl/jobs"
    input_spec_schema: ClassVar[type[BaseModel] | None] = RlJobInput
    spec_schema: ClassVar[type[BaseModel] | None] = RlJobOutput
    docker_runtime_label: ClassVar[str] = "NeMo-RL"

    @classmethod
    async def _transform(cls, job_input: BaseModel, workspace: str, async_sdk: AsyncNeMoPlatform) -> RlJobOutput:
        return await transform_input_to_output(cast(RlJobInput, job_input), workspace, async_sdk)

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
        """Compile a validated :class:`RlJobOutput` into a 4-step Ray DPO job.

        Gates on ``platform.runtime: kubernetes`` — NeMo-RL provisions a Ray
        cluster and has no local Docker fallback. An explicit
        ``training.execution_profile`` (or the ``profile`` arg) wins; when both
        are unset the compiler picks the topology-appropriate default
        (single-node ``gpu`` vs multi-node ``gpu_distributed``).
        """
        del entity_client, options
        require_distributed_runtime(cls.docker_runtime_label)
        canonical = spec if isinstance(spec, RlJobOutput) else RlJobOutput.model_validate(spec.model_dump())
        canonical.validate_for_training()

        # Leave ``None`` when unset so the compiler can default per topology.
        execution_profile = canonical.training.execution_profile or profile

        return await platform_job_config_compiler(
            workspace=workspace,
            spec=canonical,
            sdk=cast(AsyncNeMoPlatform, async_sdk),
            job_name=job_name,
            profile=execution_profile,
        )
