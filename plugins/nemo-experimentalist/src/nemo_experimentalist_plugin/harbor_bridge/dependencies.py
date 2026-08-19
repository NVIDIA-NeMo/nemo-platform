# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge-owned Harbor environments for bounded dependency analysis."""

from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from nemo_experimentalist_plugin.entities import ResourceRef
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDependencyContext,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    IDENTIFIER_MAX_LENGTH,
    DependencyExecRequest,
    DependencyExecResponse,
    DependencyStartRequest,
)

_OUTPUT_LIMIT = 30_000
_SESSION_SUFFIX_LENGTH = 16
_MAX_COMMANDS_PER_SESSION = 20
_MAX_COMMAND_TIMEOUT_SEC = 60
_SESSION_TTL_SEC = 15 * 60


def _app_path(value: str) -> str:
    """Validate one regular-file inspection path rooted below ``/app``.

    Args:
        value: Relative path or absolute path below ``/app``.

    Returns:
        Canonical absolute path string below ``/app``.

    Raises:
        ValueError: If the path is absolute outside ``/app`` or contains a
            traversal, shell-expansion, or control character.
    """
    if not value or "\x00" in value or any(token in value for token in ("$", "`", "~", "*", "?", "[", "]")):
        raise ValueError("Dependency inspection path contains unsupported characters")
    candidate = value.removeprefix("/app/") if value != "/app" else ""
    if value.startswith("/") and value != "/app" and not value.startswith("/app/"):
        raise ValueError("Dependency inspection paths must be below /app")
    if any(part in ("", ".", "..") for part in candidate.split("/") if candidate):
        raise ValueError("Dependency inspection paths must not contain traversal")
    return "/app" if not candidate else f"/app/{candidate}"


def _positive_integer(value: str, *, label: str) -> str:
    if not value.isdecimal() or not 1 <= int(value) <= 10_000:
        raise ValueError(f"Dependency inspection {label} must be an integer from 1 to 10000")
    return value


def _readonly_command(command: str) -> str:
    """Convert a small read-only inspection grammar into a shell-safe command.

    The dependency bridge is not a remote shell. Its task containers can carry
    benchmark credentials, so a caller may inspect only task files under
    ``/app``. Shell operators, environment inspection, interpreters, network
    clients, process tools, and arbitrary executable paths are intentionally
    unavailable.

    Args:
        command: One requested inspection command.

    Returns:
        Shell-quoted command line using only the approved inspection grammar.

    Raises:
        ValueError: If the command is not an approved read-only inspection.
    """
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError("Invalid dependency inspection command") from exc
    if not argv:
        raise ValueError("Dependency inspection command is empty")

    program, *args = argv
    approved: list[str]
    if program == "pwd" and not args:
        approved = ["pwd"]
    elif program in {"cat", "file", "stat"} and len(args) == 1:
        approved = [program, "--", _app_path(args[0])]
    elif program in {"head", "tail"}:
        if len(args) == 1:
            approved = [program, "--", _app_path(args[0])]
        elif len(args) == 3 and args[0] == "-n":
            approved = [program, "-n", _positive_integer(args[1], label="line count"), "--", _app_path(args[2])]
        else:
            raise ValueError(f"Unsupported dependency inspection command: {program}")
    elif program == "ls" and len(args) <= 1:
        approved = ["ls", "--", _app_path(args[0]) if args else "/app"]
    elif program == "grep" and len(args) in {2, 3}:
        include_line_numbers = len(args) == 3
        if include_line_numbers and args[0] != "-n":
            raise ValueError("grep supports only the -n option")
        pattern, path = args[-2:]
        if len(pattern) > 256 or "\x00" in pattern:
            raise ValueError("Dependency inspection grep pattern is invalid")
        approved = ["grep", "-n"] if include_line_numbers else ["grep"]
        approved.extend(("-e", pattern, "--", _app_path(path)))
    elif program == "find" and 1 <= len(args) <= 5:
        root = _app_path(args[0])
        if len(args) == 1:
            approved = ["find", root, "-maxdepth", "2", "-type", "f"]
        elif len(args) == 5 and args[1] == "-maxdepth" and args[3] == "-type" and args[4] in {"f", "d"}:
            approved = ["find", root, "-maxdepth", _positive_integer(args[2], label="maxdepth"), "-type", args[4]]
        else:
            raise ValueError("find supports only PATH [-maxdepth N -type f|d]")
    else:
        raise ValueError(f"Unsupported dependency inspection command: {program}")
    return shlex.join(approved)


def _truncate(value: str, stream: str) -> str:
    if len(value) <= _OUTPUT_LIMIT:
        return value
    return value[:_OUTPUT_LIMIT] + f"\n... ({stream} truncated)"


@dataclass
class _Session:
    context: HarborDependencyContext
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: float = field(default_factory=time.monotonic)
    command_count: int = 0


class HarborDependencySessionManager:
    """Own short-lived, read-only Harbor task inspection environments."""

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
        if time.monotonic() - session.created_at > _SESSION_TTL_SEC:
            await self.stop(session_id)
            raise RuntimeError("Dependency session expired")
        async with session.lock:
            if session.command_count >= _MAX_COMMANDS_PER_SESSION:
                raise RuntimeError("Dependency session command budget reached")
            command = _readonly_command(request.command)
            session.command_count += 1
            result = await session.context.execute(
                command,
                stdin=request.stdin,
                timeout=min(request.timeout_sec, _MAX_COMMAND_TIMEOUT_SEC),
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
