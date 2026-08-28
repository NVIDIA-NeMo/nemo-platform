# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared compile/run helpers for retrieval jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    GPUExecutionProviderSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from pydantic import BaseModel


def cpu_retrieval_step(name: str, module: str, spec: BaseModel, profile: str | None) -> PlatformJobStep:
    return PlatformJobStep(
        name=name,
        executor=CPUExecutionProviderSpec(
            profile=profile or "default",
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=["python", "-m"],
                command=[module],
            ),
        ),
        config=spec.model_dump(mode="json"),
        environment=[],
    )


def gpu_retrieval_step(name: str, module: str, spec: BaseModel, profile: str | None) -> PlatformJobStep:
    return PlatformJobStep(
        name=name,
        executor=GPUExecutionProviderSpec(
            profile=profile or "default",
            provider="gpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-customizer-tasks"),
                entrypoint=["python", "-m"],
                command=[module],
            ),
        ),
        config=spec.model_dump(mode="json"),
        environment=[],
    )


def work_dir(ctx: Any, name: str) -> Path:
    base = ctx.storage.persistent or ctx.storage.ephemeral
    path = Path(base) / name
    path.mkdir(parents=True, exist_ok=True)
    return path
