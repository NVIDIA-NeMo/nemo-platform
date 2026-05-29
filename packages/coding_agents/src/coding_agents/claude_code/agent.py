# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar

from coding_agents.base import AgentAvailability, CodingAgent
from coding_agents.claude_code.process import scrubbed_env
from coding_agents.claude_code.result import find_result_in_jsonl, to_result_event
from coding_agents.errors import (
    AgentNotInstalledError,
    AgentRunError,
    NotAuthenticatedError,
    PermissionModeUnsafeError,
)
from coding_agents.events import ResultEvent
from coding_agents.permissions import PermissionPolicy

logger = logging.getLogger(__name__)

_DEFAULT_WORK_ROOT = Path.home() / ".local" / "share" / "coding-agents"
_STOP_GRACE_SECONDS = 3.0
_AVAILABILITY_TIMEOUT_SECONDS = 10.0


class ClaudeCodeAgent(CodingAgent):
    """One-shot Claude Code invocations.

    Each `run()` writes three files under `<work_root>/<run-id>/`:
      turn_0000.prompt   — input
      turn_0000.jsonl    — stream-json output
      turn_0000.stderr   — stderr
    The files are left on disk after the run for debugging; callers can
    clean up `<work_root>/<run-id>/` themselves if they want to.
    """

    name: ClassVar[str] = "claude-code"

    def __init__(
        self,
        *,
        binary: str = "claude",
        work_root: Path | None = None,
    ) -> None:
        self.binary = binary
        self.work_root = work_root or _DEFAULT_WORK_ROOT
        self.work_root.mkdir(parents=True, exist_ok=True)

    async def check_available(self) -> AgentAvailability:
        binary_path = shutil.which(self.binary)
        if binary_path is None:
            raise AgentNotInstalledError(f"`{self.binary}` is not on PATH. Install Claude Code and try again.")

        stdout, _ = await self._availability_subprocess(binary_path, "--version", on_timeout_err=AgentNotInstalledError)
        version_line = stdout.decode("utf-8", "replace").strip().splitlines()[0:1]
        version = version_line[0] if version_line else None

        # `claude auth status` exits non-zero (and writes a login hint) when
        # the user isn't logged in. Any clean exit means we're authenticated.
        await self._availability_subprocess(binary_path, "auth", "status", on_timeout_err=NotAuthenticatedError)

        return AgentAvailability(installed=True, authenticated=True, version=version)

    async def run(
        self,
        prompt: str,
        *,
        working_dir: Path,
        timeout: float | None = None,
        permissions: PermissionPolicy | None = None,
        system_prompt: str | None = None,
        append_system_prompt: str | None = None,
        max_budget_usd: float | None = None,
        model: str | None = None,
        extra_env: Mapping[str, str] | None = None,
        extra_cli_args: Sequence[str] | None = None,
        resume_session_id: str | None = None,
    ) -> ResultEvent:
        if not working_dir.is_dir():
            raise ValueError(f"working_dir does not exist or is not a directory: {working_dir}")
        permissions = permissions or PermissionPolicy()
        if not permissions.is_headless_safe():
            raise PermissionModeUnsafeError(
                f"PermissionMode.{permissions.mode.name} requires an interactive prompt "
                f"that headless mode cannot answer. Use BYPASS or PLAN."
            )

        # For a fresh conversation, session_id == work_dir name (same UUID).
        # For a resume, work_dir gets a fresh UUID so we don't clobber the
        # prior turn's files; session_id is what Claude resumes against.
        if resume_session_id is None:
            session_id = str(uuid.uuid4())
            work_dir_name = session_id
        else:
            session_id = resume_session_id
            work_dir_name = str(uuid.uuid4())

        # Restrictive perms: prompts and outputs can contain sensitive data
        # (file contents, API keys agents pull from env, etc.). 0o700/0o600
        # keeps everything user-only.
        run_dir = self.work_root / work_dir_name
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        run_dir.chmod(0o700)
        prompt_path = run_dir / "turn_0000.prompt"
        jsonl_path = run_dir / "turn_0000.jsonl"
        stderr_path = run_dir / "turn_0000.stderr"
        meta_path = run_dir / "meta.json"

        meta_path.write_text(
            json.dumps(
                {
                    "backend": self.name,
                    "session_id": session_id,
                    "resumed": resume_session_id is not None,
                    "working_dir": str(working_dir),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        meta_path.chmod(0o600)
        prompt_path.write_text(prompt, encoding="utf-8")
        prompt_path.chmod(0o600)

        cmd = self._build_cmd(
            session_id=session_id,
            resume=resume_session_id is not None,
            permissions=permissions,
            system_prompt=system_prompt,
            append_system_prompt=append_system_prompt,
            max_budget_usd=max_budget_usd,
            model=model,
            extra_cli_args=extra_cli_args,
        )
        env = scrubbed_env(extra_env)

        proc = await self._spawn(
            cmd=cmd,
            env=env,
            working_dir=working_dir,
            prompt_path=prompt_path,
            jsonl_path=jsonl_path,
            stderr_path=stderr_path,
        )

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await self._terminate(proc)
            raise TimeoutError(f"agent did not complete within {timeout}s") from None
        except asyncio.CancelledError:
            await self._terminate(proc)
            raise

        raw = find_result_in_jsonl(jsonl_path)
        if raw is None:
            raise AgentRunError(
                f"agent process exited (code={proc.returncode}) without producing a "
                f"result event. see {stderr_path} for details"
            )
        return to_result_event(raw, session_id=session_id, artifact_dir=run_dir)

    def _build_cmd(
        self,
        *,
        session_id: str,
        resume: bool,
        permissions: PermissionPolicy,
        system_prompt: str | None,
        append_system_prompt: str | None,
        max_budget_usd: float | None,
        model: str | None,
        extra_cli_args: Sequence[str] | None,
    ) -> list[str]:
        cmd = [
            self.binary,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            str(permissions.mode.value),
            "--resume" if resume else "--session-id",
            session_id,
        ]
        if permissions.allowed_tools:
            cmd += ["--allowed-tools", *permissions.allowed_tools]
        if permissions.disallowed_tools:
            cmd += ["--disallowed-tools", *permissions.disallowed_tools]
        if system_prompt:
            cmd += ["--system-prompt", system_prompt]
        if append_system_prompt:
            cmd += ["--append-system-prompt", append_system_prompt]
        if max_budget_usd is not None:
            cmd += ["--max-budget-usd", str(max_budget_usd)]
        if model:
            cmd += ["--model", model]
        if extra_cli_args:
            cmd += list(extra_cli_args)
        return cmd

    @staticmethod
    async def _spawn(
        *,
        cmd: list[str],
        env: dict[str, str],
        working_dir: Path,
        prompt_path: Path,
        jsonl_path: Path,
        stderr_path: Path,
    ) -> asyncio.subprocess.Process:
        # Open files for stdin/stdout/stderr; the child gets dup'd fds, so we
        # can close ours immediately after spawn. fds are initialized to None
        # and opened inside the try so a failure on later os.open() calls
        # still closes the earlier ones.
        stdin_fd: int | None = None
        stdout_fd: int | None = None
        stderr_fd: int | None = None
        try:
            stdin_fd = os.open(str(prompt_path), os.O_RDONLY)
            stdout_fd = os.open(str(jsonl_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            stderr_fd = os.open(str(stderr_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            return await asyncio.create_subprocess_exec(
                *cmd,
                stdin=stdin_fd,
                stdout=stdout_fd,
                stderr=stderr_fd,
                env=env,
                cwd=str(working_dir),
            )
        finally:
            for fd in (stdin_fd, stdout_fd, stderr_fd):
                if fd is not None:
                    os.close(fd)

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        # `send_signal` races with reap: the process can exit between the
        # returncode check above and the signal landing. ProcessLookupError
        # in that window just means the child is already gone.
        try:
            proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=_STOP_GRACE_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                return
            await proc.wait()

    async def _availability_subprocess(
        self,
        binary_path: str,
        *args: str,
        on_timeout_err: type[Exception],
    ) -> tuple[bytes, bytes]:
        """Run `binary_path` with args; enforce a timeout; raise typed errors
        on non-zero exit or timeout. Used by check_available()."""
        proc = await asyncio.create_subprocess_exec(
            binary_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_AVAILABILITY_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await self._terminate(proc)
            raise on_timeout_err(
                f"`{self.binary} {' '.join(args)}` timed out after {_AVAILABILITY_TIMEOUT_SECONDS}s"
            ) from None
        if proc.returncode != 0:
            combined = (stdout + stderr).decode("utf-8", "replace")
            raise on_timeout_err(f"`{self.binary} {' '.join(args)}` exited {proc.returncode}: {combined[:300]}")
        return stdout, stderr
