# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unsloth remote-submit training job (NemoJob).

Submit-only — Unsloth executes as a 4-step ``PlatformJobSpec`` (download
→ train → upload → model-entity) on the platform's GPU cluster, mirroring
:class:`nemo_automodel_plugin.jobs.jobs.AutomodelJob`.

The plugin's CLI hard-fails ``run`` with a friendlier message (see
:mod:`nemo_unsloth_plugin.cli.inputs`); a stray local-run would otherwise
need the unsloth/torch stack in the parent interpreter, which we no
longer support after the 2026 container-submit migration.

Two responsibilities:

1. ``to_spec`` — async; validates the model entity + dataset fileset
   against the live SDK, resolves the output naming and fileset, and
   returns a canonical :class:`UnslothJobOutput`.
2. ``compile`` — async; delegates to
   :func:`nmp.unsloth.compile.platform_job_config_compiler`, which builds
   the 4-step container job spec the platform Jobs runner executes.
"""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.config import NemoPlatformConfig, Runtime
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.docker import validate_gpu_available_for_docker
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nmp.unsloth.compile import platform_job_config_compiler
from nmp.unsloth.config import config as unsloth_config
from nmp.unsloth.schemas import UnslothJobOutput
from pydantic import BaseModel

from nemo_unsloth_plugin.schema import UnslothJobInput
from nemo_unsloth_plugin.transform import transform_input_to_output


def _require_docker_runtime() -> None:
    """Refuse to compile when the platform isn't configured for Docker.

    Mirrors :func:`nemo_automodel_plugin.jobs.jobs._require_docker_runtime`.
    The compile step builds Docker container specs; surface the
    misconfiguration before the Jobs API rejects the spec.
    """
    platform_config = NemoPlatformConfig.get()
    if platform_config.runtime != Runtime.DOCKER:
        raise PlatformJobCompilationError(
            "Unsloth training requires platform.runtime: docker with GPU-backed container execution.",
        )
    from nemo_platform_plugin.config import validate_docker_available

    if not validate_docker_available():
        raise PlatformJobCompilationError(
            "Unsloth training requires a reachable Docker daemon (platform.runtime: docker).",
        )


class UnslothJob(NemoJob):
    """GPU Unsloth fine-tuning job under the customization router.

    Submit-only: ``run`` is intentionally not implemented. The plugin's
    CLI replaces ``run`` with a hard-fail message; reaching the
    platform's default ``run`` would raise ``NotImplementedError`` from
    :class:`NemoJob`.
    """

    name: ClassVar[str] = "unsloth.jobs"
    description: ClassVar[str] = "Unsloth SFT (LoRA / full / merged) training jobs on the platform GPU cluster."
    job_collection_path: ClassVar[str | None] = "/unsloth/jobs"
    input_spec_schema: ClassVar[type[BaseModel] | None] = UnslothJobInput
    spec_schema: ClassVar[type[BaseModel] | None] = UnslothJobOutput
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> UnslothJobOutput:
        """Validate platform refs, resolve naming, return canonical spec."""
        del entity_client, is_local
        job_input = (
            input_spec
            if isinstance(input_spec, UnslothJobInput)
            else UnslothJobInput.model_validate(input_spec.model_dump())
        )
        return await transform_input_to_output(
            job_input,
            workspace,
            cast(AsyncNeMoPlatform, async_sdk),
        )

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

        Args:
            workspace: Submitter's workspace; passed through to compile
                for fileset/entity resolution.
            spec: Canonical job spec (``UnslothJobOutput`` or anything
                with a compatible ``model_dump``).
            entity_client: Unused; kept for the
                :class:`NemoJob.compile` interface contract.
            job_name: Platform-assigned job name (used for logging /
                future scheduling decisions inside the compiler).
            async_sdk: Async platform SDK for validating model + dataset
                refs against live state at compile time.
            profile: Caller-supplied execution profile override.
                Resolution order: this arg →
                ``unsloth_config.default_training_execution_profile``.
                Unsloth's :class:`HardwareSpec` does not (yet) expose an
                ``execution_profile`` field; expose it on the schema if
                callers need per-job overrides.
            options: Unused; reserved for backend-specific compile
                options the platform may forward later.
        """
        del entity_client, options
        _require_docker_runtime()
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
