# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge-owned Harbor environments for bounded dependency analysis."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDependencyContext,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    IDENTIFIER_MAX_LENGTH,
    DependencyExecRequest,
    DependencyExecResponse,
    DependencyStartRequest,
)

_OUTPUT_LIMIT = 30_000
_SESSION_SUFFIX_LENGTH = 16


def _truncate(value: str, stream: str) -> str:
    if len(value) <= _OUTPUT_LIMIT:
        return value
    return value[:_OUTPUT_LIMIT] + f"\n... ({stream} truncated)"


@dataclass
class _Session:
    context: HarborDependencyContext
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class HarborDependencySessionManager:
    """Own active environments and expose no Docker configuration."""

    def __init__(self, *, max_concurrent_sessions: int = 2) -> None:
        self._max = max_concurrent_sessions
        self._sessions: dict[str, _Session] = {}
        self._starting = 0
        self._lock = asyncio.Lock()

    async def start(self, request: DependencyStartRequest, *, task_dir: Path, work_dir: Path) -> str:
        async with self._lock:
            if len(self._sessions) + self._starting >= self._max:
                raise RuntimeError("Dependency session capacity reached")
            self._starting += 1
        runtime = HarborDependencyRuntime(
            task_path=ResourceRef(uri=task_dir.resolve().as_uri()),
            force_build=True,
            delete=True,
            run_healthcheck=True,
        )
        context = HarborDependencyContext(runtime, temp_root=work_dir / "runtime")
        entered = False
        try:
            await context.__aenter__()
            entered = True
            request_prefix = request.request_id[: IDENTIFIER_MAX_LENGTH - _SESSION_SUFFIX_LENGTH - 1]
            session_id = f"{request_prefix}-{uuid4().hex[:_SESSION_SUFFIX_LENGTH]}"
            async with self._lock:
                self._sessions[session_id] = _Session(context)
            entered = False
        except BaseException:
            if entered:
                await context.__aexit__(None, None, None)
            raise
        finally:
            async with self._lock:
                self._starting -= 1
        return session_id

    async def execute(self, session_id: str, request: DependencyExecRequest) -> DependencyExecResponse:
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        async with session.lock:
            result = await session.context.execute(
                request.command,
                stdin=request.stdin,
                timeout=request.timeout_sec,
            )
        return DependencyExecResponse(
            stdout=_truncate(result.stdout, "stdout"),
            stderr=_truncate(result.stderr, "stderr"),
            returncode=result.returncode,
        )

    async def stop(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise KeyError(session_id)
        async with session.lock:
            await session.context.__aexit__(None, None, None)

    async def close(self) -> None:
        async with self._lock:
            session_ids = list(self._sessions)
        results = await asyncio.gather(*(self.stop(session_id) for session_id in session_ids), return_exceptions=True)
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise ExceptionGroup("Failed to stop Harbor dependency sessions", errors)
