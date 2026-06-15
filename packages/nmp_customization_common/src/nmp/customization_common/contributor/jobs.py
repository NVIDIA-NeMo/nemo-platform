# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base remote-submit training job for customization backends.

Both backends submit a 4-step ``PlatformJobSpec`` (download → train → upload →
model-entity) executed on the platform GPU cluster. ``to_spec`` and the
Docker-runtime guard are shared here; ``compile`` genuinely diverges (compiler
call convention, schema validation, profile resolution) and stays per-backend.
"""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.config import NemoPlatformConfig, Runtime
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from pydantic import BaseModel


def require_docker_runtime(backend_label: str) -> None:
    """Refuse to compile when the platform isn't configured for Docker.

    The compile step builds Docker container specs; surface the misconfiguration
    before the Jobs API rejects the spec.
    """
    platform_config = NemoPlatformConfig.get()
    if platform_config.runtime != Runtime.DOCKER:
        raise PlatformJobCompilationError(
            f"{backend_label} training requires platform.runtime: docker with GPU-backed container execution.",
        )
    from nemo_platform_plugin.config import validate_docker_available

    if not validate_docker_available():
        raise PlatformJobCompilationError(
            f"{backend_label} training requires a reachable Docker daemon (platform.runtime: docker).",
        )


class BaseSubmitJob(NemoJob):
    """Shared submit-only job scaffold.

    Subclasses set the ``NemoJob`` ClassVars (``name``, ``description``,
    ``job_collection_path``, ``input_spec_schema``, ``spec_schema``), implement
    :meth:`_transform` and :meth:`compile`, and may set :attr:`docker_runtime_label`.
    """

    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]
    #: Human-readable backend name used in the Docker-runtime guard messages.
    docker_runtime_label: ClassVar[str] = "Training"

    @classmethod
    async def _transform(cls, job_input: BaseModel, workspace: str, async_sdk: AsyncNeMoPlatform) -> BaseModel:
        """Validate platform refs and return the canonical output spec. Per backend."""
        raise NotImplementedError

    @classmethod
    async def to_spec(
        cls,
        input_spec: BaseModel,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> BaseModel:
        """Validate platform refs, resolve naming, return the canonical spec."""
        del entity_client, is_local
        schema = cls.input_spec_schema
        if schema is None:
            raise PlatformJobCompilationError(f"{cls.__name__} is missing an input_spec_schema.")
        job_input = input_spec if isinstance(input_spec, schema) else schema.model_validate(input_spec.model_dump())
        return await cls._transform(job_input, workspace, cast(AsyncNeMoPlatform, async_sdk))
