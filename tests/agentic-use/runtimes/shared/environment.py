# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Environment provider boundary for agentic-use runtimes.

This is the design-doc's ``EnvironmentProvider`` boundary (section B2): it sits
*below* :class:`AgentAttemptRuntime` so a runtime never needs to know whether
the agent/verifier execute under Docker, locally, Harbor, or NeMo Gym. Today the
only implementation is :class:`DockerEnvironmentProvider`, which wraps
``shared/docker.py``.

Deviation from the doc sketch: the doc proposes ``run_agent(instruction, config)
-> AgentEvalAttempt``. We keep the boundary at "execute a command in the
prepared environment" (returning an :class:`EnvCommandResult`) because each
backend builds its own command/env/mounts, and attempt construction is owned by
``shared/artifacts.py``. This keeps command-building and attempt-shaping out of
the environment layer so new providers only implement process execution.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.docker import docker_run
from runtimes.shared.layout import task_image_tag


@dataclass(frozen=True)
class EnvCommandResult:
    """Outcome of running a single command inside a prepared environment."""

    exit_code: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class EnvRunSpec:
    """How to execute one command inside an environment handle."""

    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    mounts: list[tuple[str, str]] = field(default_factory=list)
    workdir: str | None = None
    timeout: int | None = None
    extra_args: list[str] = field(default_factory=list)


@runtime_checkable
class AgentEnvironmentHandle(Protocol):
    """A prepared, single-task environment that can run agent/verifier commands."""

    async def run_agent(self, spec: EnvRunSpec) -> EnvCommandResult: ...

    async def run_verifier(self, spec: EnvRunSpec) -> EnvCommandResult: ...

    async def close(self) -> None: ...


@runtime_checkable
class AgentEnvironmentProvider(Protocol):
    """Creates per-task environment handles. Pluggable: Docker now, Gym later."""

    async def prepare(
        self,
        task: AgentEvalTask,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEnvironmentHandle: ...


class DockerEnvironmentHandle:
    """Docker-backed environment handle bound to one task image."""

    def __init__(self, image: str) -> None:
        self.image = image

    async def run_agent(self, spec: EnvRunSpec) -> EnvCommandResult:
        return await self._run(spec)

    async def run_verifier(self, spec: EnvRunSpec) -> EnvCommandResult:
        return await self._run(spec)

    async def _run(self, spec: EnvRunSpec) -> EnvCommandResult:
        try:
            result = await asyncio.to_thread(
                docker_run,
                self.image,
                spec.command,
                env=spec.env,
                mounts=spec.mounts,
                workdir=spec.workdir,
                timeout=spec.timeout,
                extra_args=spec.extra_args,
            )
        except subprocess.TimeoutExpired:
            return EnvCommandResult(exit_code=124, timed_out=True)
        return EnvCommandResult(exit_code=result.returncode)

    async def close(self) -> None:
        # `docker run --rm` cleans up the container; nothing persistent to release.
        return None


class DockerEnvironmentProvider:
    """Default provider that maps each task to its built Docker image."""

    def __init__(self, *, image_tag_fn: Callable[[str], str] = task_image_tag) -> None:
        self._image_tag_fn = image_tag_fn

    async def prepare(
        self,
        task: AgentEvalTask,
        config: AgentEvalRunConfig | None = None,
    ) -> DockerEnvironmentHandle:
        del config
        return DockerEnvironmentHandle(self._image_tag_fn(task.id))
