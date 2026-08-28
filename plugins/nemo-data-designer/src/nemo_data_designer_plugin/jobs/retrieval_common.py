# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared compile/run helpers for retrieval jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    GPUExecutionProviderSpec,
    PlatformJobStep,
    SubprocessExecutionProviderSpec,
)
from nemo_platform_plugin.jobs.client import AsyncJobsClient
from nemo_platform_plugin.jobs.image import get_qualified_image
from pydantic import BaseModel

_ENTRYPOINT = ["python", "-m"]


async def subprocess_profile_available(async_sdk: object, profile: str) -> bool:
    """True when the jobs service has a subprocess backend for *profile*.

    Local ``nemo services run`` registers ``provider=subprocess, profile=default`` and
    remaps CPU container steps onto it. Prefer emitting subprocess directly so generate
    and convert run in the host venv (no ``nmp-cpu-tasks`` image, and mining can use
    host GPUs instead of ``nmp-customizer-tasks``).
    """
    if async_sdk is None:
        return False
    try:
        jobs = client_from_platform(cast(AsyncNeMoPlatform, async_sdk), AsyncJobsClient)
        listed = await jobs.get_execution_profiles()
        profiles = listed.data() if hasattr(listed, "data") else listed
    except Exception:
        return False
    if not isinstance(profiles, (list, tuple)):
        return False
    for item in profiles:
        provider = item.get("provider") if isinstance(item, dict) else getattr(item, "provider", None)
        name = item.get("profile") if isinstance(item, dict) else getattr(item, "profile", None)
        if provider == "subprocess" and name == profile:
            return True
    return False


def _subprocess_step(name: str, module: str, spec: BaseModel, profile: str) -> PlatformJobStep:
    return PlatformJobStep(
        name=name,
        executor=SubprocessExecutionProviderSpec(
            provider="subprocess",
            profile=profile,
            command=[*_ENTRYPOINT, module],
        ),
        config=spec.model_dump(mode="json"),
        environment=[],
    )


def cpu_retrieval_step(name: str, module: str, spec: BaseModel, profile: str | None) -> PlatformJobStep:
    return PlatformJobStep(
        name=name,
        executor=CPUExecutionProviderSpec(
            profile=profile or "default",
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=_ENTRYPOINT,
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
                entrypoint=_ENTRYPOINT,
                command=[module],
            ),
        ),
        config=spec.model_dump(mode="json"),
        environment=[],
    )


async def retrieval_step(
    name: str,
    module: str,
    spec: BaseModel,
    *,
    profile: str | None,
    async_sdk: object,
    gpu: bool = False,
) -> PlatformJobStep:
    resolved = profile or "default"
    if await subprocess_profile_available(async_sdk, resolved):
        return _subprocess_step(name, module, spec, resolved)
    if gpu:
        return gpu_retrieval_step(name, module, spec, resolved)
    return cpu_retrieval_step(name, module, spec, resolved)


def work_dir(ctx: Any, name: str) -> Path:
    base = ctx.storage.persistent or ctx.storage.ephemeral
    path = Path(base) / name
    path.mkdir(parents=True, exist_ok=True)
    return path
