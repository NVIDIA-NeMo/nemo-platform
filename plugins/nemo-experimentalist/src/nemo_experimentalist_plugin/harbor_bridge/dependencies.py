# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge-owned Harbor task environments for analyzer dependency access."""

from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDependencyContext,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    DEPENDENCY_OUTPUT_LIMIT_CHARS,
    HarborDependencyExecRequest,
    HarborDependencyExecResponse,
    HarborDependencyRequest,
)
from nemo_experimentalist_plugin.harbor_bridge.runner import _harden_task

logger = logging.getLogger(__name__)


def _truncate_output(value: str, *, stream: str) -> str:
    if len(value) <= DEPENDENCY_OUTPUT_LIMIT_CHARS:
        return value
    return value[:DEPENDENCY_OUTPUT_LIMIT_CHARS] + f"\n... ({stream} truncated)"


class HarborDependencyCapacityError(RuntimeError):
    """The bridge has no free dependency-session capacity."""


@dataclass
class _SessionState:
    context: HarborDependencyContext
    cwd: str = "/app"
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class HarborDependencySessionManager:
    """Own active Harbor environments and expose only in-container execution."""

    def __init__(self, *, max_concurrent_sessions: int) -> None:
        self._max_concurrent_sessions = max_concurrent_sessions
        self._sessions: dict[str, _SessionState] = {}
        self._starting = 0
        self._lock = asyncio.Lock()

    async def start(
        self,
        request: HarborDependencyRequest,
        *,
        task_dir: Path,
    ) -> str:
        """Validate and start one uploaded Harbor task environment."""
        async with self._lock:
            if len(self._sessions) + self._starting >= self._max_concurrent_sessions:
                raise HarborDependencyCapacityError(
                    f"Harbor dependency session capacity reached ({self._max_concurrent_sessions})"
                )
            self._starting += 1

        context: HarborDependencyContext | None = None
        try:
            _harden_task(task_dir)
            runtime = HarborDependencyRuntime(
                task_path=ResourceRef(
                    uri=task_dir.resolve().as_uri(),
                    description="Bridge-local Harbor task dependency environment.",
                ),
                force_build=request.force_build,
                delete=True,
                run_healthcheck=request.run_healthcheck,
                build_timeout_sec=request.build_timeout_sec,
            )
            context = HarborDependencyContext(
                runtime,
                temp_root=task_dir.parent.parent / "runtime",
            )
            await context.__aenter__()
            session_id = f"{request.request_id}-{uuid4().hex[:16]}"
            async with self._lock:
                self._sessions[session_id] = _SessionState(context=context)
            return session_id
        except BaseException:
            if context is not None:
                try:
                    await context.__aexit__(None, None, None)
                except Exception:
                    logger.exception("Harbor dependency cleanup failed after startup error")
            raise
        finally:
            async with self._lock:
                self._starting -= 1

    async def execute(
        self,
        session_id: str,
        request: HarborDependencyExecRequest,
    ) -> HarborDependencyExecResponse:
        """Execute one command inside an active task environment."""
        async with self._lock:
            state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(session_id)

        async with state.lock:
            marker = f"__NEMO_DEPENDENCY_CWD_{uuid4().hex}__"
            command = request.command
            if request.stdin is not None:
                command = f"printf %s {shlex.quote(request.stdin)} | (\n{command}\n)"
            wrapped = (
                f"{command}\n"
                "_nemo_dependency_status=$?\n"
                f"printf '\\036{marker}%s\\036' \"$PWD\"\n"
                'exit "$_nemo_dependency_status"'
            )
            result = await state.context.execute(
                wrapped,
                cwd=state.cwd,
                timeout_sec=request.timeout_sec,
            )

            stdout = result.stdout or ""
            marker_start = stdout.rfind(f"\x1e{marker}")
            if marker_start >= 0:
                cwd_start = marker_start + len(marker) + 1
                marker_end = stdout.find("\x1e", cwd_start)
                if marker_end >= 0:
                    state.cwd = stdout[cwd_start:marker_end]
                    stdout = stdout[:marker_start] + stdout[marker_end + 1 :]

            return HarborDependencyExecResponse(
                stdout=_truncate_output(stdout, stream="output"),
                stderr=_truncate_output(result.stderr or "", stream="stderr"),
                returncode=result.return_code,
            )

    async def stop(self, session_id: str) -> None:
        """Stop and forget one dependency environment."""
        async with self._lock:
            state = self._sessions.pop(session_id, None)
        if state is None:
            raise KeyError(session_id)
        async with state.lock:
            await state.context.__aexit__(None, None, None)

    async def close(self) -> None:
        """Stop every dependency environment still owned by the bridge."""
        async with self._lock:
            session_ids = list(self._sessions)
        for session_id in session_ids:
            try:
                await self.stop(session_id)
            except Exception:
                logger.exception("Failed to stop Harbor dependency session %s", session_id)
