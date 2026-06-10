# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Process/filesystem environment boundary for agent-eval runtimes.

This boundary sits *below* :class:`AgentAttemptRuntime` so a runtime never needs
to know whether the agent/verifier execute under Docker, locally, or another
filesystem-backed sandbox. It is intentionally a **process/filesystem**
abstraction, not a fully provider-neutral one: :class:`EnvRunSpec` carries
``mounts``/``extra_args`` as filesystem-environment hints. Providers that are
not filesystem-backed may ignore those fields.

A handle exposes a single :meth:`AbstractEnvironmentHandle.run` that takes a
``role`` ("agent" or "verifier"); :meth:`run_agent`/:meth:`run_verifier` are thin
role wrappers kept for caller convenience and protocol compatibility.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunConfig, AgentEvalTask

EnvRole = Literal["agent", "verifier"]


def default_image_tag(task_id: str) -> str:
    """Default task → image-tag mapping (callers may inject their own)."""
    return f"{task_id}:latest"


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
    """How to execute one command inside an environment handle.

    ``mounts``/``extra_args`` are filesystem-environment hints (e.g. Docker bind
    mounts and extra CLI args). Non-filesystem providers may ignore them.
    """

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
    """Creates per-task environment handles. Pluggable: Docker now, others later."""

    async def prepare(
        self,
        task: AgentEvalTask,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEnvironmentHandle: ...


class AbstractEnvironmentHandle:
    """Base handle that routes both roles through a single :meth:`run`.

    Concrete handles implement :meth:`run`; ``run_agent``/``run_verifier`` are
    role-specialized wrappers so the duplicated phase methods don't have to be
    reimplemented per backend.
    """

    async def run(self, spec: EnvRunSpec, role: EnvRole) -> EnvCommandResult:
        raise NotImplementedError

    async def run_agent(self, spec: EnvRunSpec) -> EnvCommandResult:
        return await self.run(spec, "agent")

    async def run_verifier(self, spec: EnvRunSpec) -> EnvCommandResult:
        return await self.run(spec, "verifier")

    async def close(self) -> None:
        return None


class DockerEnvironmentHandle(AbstractEnvironmentHandle):
    """Docker-backed environment handle bound to one task image."""

    def __init__(self, image: str) -> None:
        self.image = image

    async def run(self, spec: EnvRunSpec, role: EnvRole = "agent") -> EnvCommandResult:
        del role  # Docker runs both roles identically against the same image.
        from nemo_evaluator_sdk.agent_eval.runtimes.docker import docker_run

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


class DockerEnvironmentProvider:
    """Default provider that maps each task to its built Docker image."""

    def __init__(self, *, image_tag_fn: Callable[[str], str] = default_image_tag) -> None:
        self._image_tag_fn = image_tag_fn

    async def prepare(
        self,
        task: AgentEvalTask,
        config: AgentEvalRunConfig | None = None,
    ) -> DockerEnvironmentHandle:
        del config
        return DockerEnvironmentHandle(self._image_tag_fn(task.id))
