# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base remote-submit training job for customization backends.

Both backends submit a 4-step ``PlatformJobSpec`` (download → train → upload →
model-entity) executed on the platform GPU cluster. ``to_spec`` and the
runtime guards are shared here; ``compile`` genuinely diverges (compiler
call convention, schema validation, profile resolution) and stays per-backend.
"""

from __future__ import annotations

from typing import ClassVar, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.config import NemoPlatformConfig, Runtime
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from pydantic import BaseModel


def require_container_runtime(backend_label: str, *, num_nodes: int = 1) -> None:
    """Refuse to compile unless the platform can run the requested container job.

    SFT backends (automodel / unsloth) build a container ``PlatformJobSpec`` the
    platform runs on either supported target:

    - **Kubernetes** — the platform schedules GPU pods, including multi-node
      ``gpu_distributed`` jobs via Volcano.
    - **Docker** — the platform's local Docker GPU executor (single host).

    Single-node jobs accept either runtime. **Multi-node jobs** (``num_nodes >
    1``) compile to a ``gpu_distributed`` executor that only the Volcano
    (Kubernetes) backend can place — Docker has no multi-node/``gpu_distributed``
    backend — so they require ``platform.runtime: kubernetes``. Failing here
    surfaces the misconfiguration at compile time instead of as an opaque
    "no backend found" scheduling error (or, for ``runtime: none``, before the
    Jobs API rejects the spec).
    """
    platform_config = NemoPlatformConfig.get()
    runtime = platform_config.runtime

    if num_nodes > 1 and runtime != Runtime.KUBERNETES:
        raise PlatformJobCompilationError(
            f"{backend_label} multi-node training (num_nodes={num_nodes}) requires "
            "platform.runtime: kubernetes — multi-node jobs run on the Volcano "
            "(gpu_distributed) backend, which has no Docker equivalent. "
            f"Current runtime: {runtime.value}.",
        )

    if runtime == Runtime.KUBERNETES:
        return

    if runtime == Runtime.DOCKER:
        from nemo_platform_plugin.config import validate_docker_available

        if not validate_docker_available():
            raise PlatformJobCompilationError(
                f"{backend_label} training requires a reachable Docker daemon (platform.runtime: docker).",
            )
        return

    raise PlatformJobCompilationError(
        f"{backend_label} training requires a container runtime: set platform.runtime to "
        "'kubernetes' (schedules GPU pods) or 'docker' (local GPU executor). "
        f"Current runtime: {runtime.value}.",
    )


def require_distributed_runtime(backend_label: str) -> None:
    """Refuse to compile when the platform isn't a remote Kubernetes cluster.

    Sibling to :func:`require_container_runtime` for backends that provision a Ray
    cluster (e.g. NeMo-RL DPO). Unlike the SFT backends, these accept **only**
    Kubernetes (no Docker fallback): they need the platform's Kubernetes/Volcano
    scheduler to place GPU pods and inject the distributed env
    (``RANK``/``WORLD_SIZE``/``MASTER_ADDR``). Surface the misconfiguration before
    the Jobs API rejects the spec.
    """
    platform_config = NemoPlatformConfig.get()
    if platform_config.runtime != Runtime.KUBERNETES:
        raise PlatformJobCompilationError(
            f"{backend_label} training requires platform.runtime: kubernetes — it provisions a Ray "
            "cluster on the remote GPU cluster and has no local Docker fallback.",
        )


class BaseSubmitJob(NemoJob):
    """Shared submit-only job scaffold.

    Subclasses set the ``NemoJob`` ClassVars (``name``, ``description``,
    ``job_collection_path``, ``input_spec_schema``, ``spec_schema``), implement
    :meth:`_transform` and :meth:`compile`, and may set :attr:`runtime_label`.
    """

    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "models"]
    #: Human-readable backend name used in the runtime guard messages.
    runtime_label: ClassVar[str] = "Training"

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
