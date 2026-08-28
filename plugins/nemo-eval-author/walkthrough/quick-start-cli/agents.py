# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Invoke Cursor Agent or Claude Code for the walkthrough quick-start CLI."""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_events import AgentActivityTracker
from display import AgentProfile

MAX_OUTPUT_LINE_CHARS = 240
MAX_STORED_LINES = 200


class AgentCliError(RuntimeError):
    """Raised when a coding agent CLI is missing or fails to start."""


@dataclass(slots=True)
class AgentProcess:
    """Background coding-agent subprocess with a bounded output tap."""

    label: str
    command: list[str]
    proc: subprocess.Popen[str]
    activity: AgentActivityTracker | None = None
    _pending: queue.SimpleQueue[str] = field(default_factory=queue.SimpleQueue, init=False)
    _history: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_STORED_LINES), init=False)
    _reader_threads: list[threading.Thread] = field(default_factory=list, init=False)

    def drain_activity(self, limit: int = 3) -> list[str]:
        if self.activity is None:
            return []
        return self.activity.drain(limit)

    def __post_init__(self) -> None:
        assert self.proc.stdout is not None
        assert self.proc.stderr is not None
        self._reader_threads = [
            threading.Thread(target=self._read_stream, args=(self.proc.stdout, "out"), daemon=True),
            threading.Thread(target=self._read_stream, args=(self.proc.stderr, "err"), daemon=True),
        ]
        for thread in self._reader_threads:
            thread.start()

    def _read_stream(self, stream: Any, kind: str) -> None:
        for raw in stream:
            line = raw.rstrip()
            if not line:
                continue
            if kind == "err":
                line = f"[stderr] {line}"
            if len(line) > MAX_OUTPUT_LINE_CHARS:
                line = line[: MAX_OUTPUT_LINE_CHARS - 3] + "..."
            self._history.append(line)
            self._pending.put(line)
            if self.activity is not None and kind == "out":
                self.activity.feed(raw.rstrip())

    def drain(self, limit: int = 3) -> list[str]:
        """Return up to ``limit`` new output lines."""
        drained: list[str] = []
        while len(drained) < limit:
            try:
                drained.append(self._pending.get_nowait())
            except queue.Empty:
                break
        return drained

    def done(self) -> bool:
        return self.proc.poll() is not None

    @property
    def returncode(self) -> int | None:
        return self.proc.returncode

    def recent_lines(self, limit: int = 5) -> list[str]:
        if limit <= 0:
            return []
        return list(self._history)[-limit:]

    def terminate(self) -> None:
        if self.done():
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def preflight_agent_cli(profile: AgentProfile) -> list[str]:
    """Verify the selected agent CLI exists and return its launch command prefix."""
    if profile.key == "cursor":
        if shutil.which("agent"):
            return ["agent"]
        cursor = shutil.which("cursor")
        if cursor:
            return [cursor, "agent"]
        raise AgentCliError(
            "Cursor Agent CLI not found on PATH. Install Cursor and ensure "
            "the `agent` or `cursor` command is available."
        )

    if profile.key == "claude":
        if shutil.which("claude"):
            return ["claude"]
        raise AgentCliError(
            "Claude Code CLI not found on PATH. Install Claude Code "
            "(https://claude.com/claude-code) and authenticate before running the demo."
        )

    raise AgentCliError(f"unsupported agent profile: {profile.key}")


def build_agent_command(profile: AgentProfile, prompt: str) -> list[str]:
    """Build the full argv for a headless coding-agent invocation."""
    prefix = preflight_agent_cli(profile)
    if profile.key == "cursor":
        return [*prefix, "-p", "-f", "--trust", "--output-format", "stream-json", prompt]
    return [*prefix, "--print", "--dangerously-skip-permissions"]


def agent_env(profile: AgentProfile, workspace: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for the coding-agent subprocess."""
    env = dict(base or os.environ)
    existing = env.get("PYTHONPATH")
    workspace_path = str(workspace)
    env["PYTHONPATH"] = workspace_path if not existing else f"{workspace_path}{os.pathsep}{existing}"

    if profile.key == "claude":
        env = {
            key: value
            for key, value in env.items()
            if not key.startswith("ANTHROPIC_") and key != "CLAUDECODE" and not key.startswith("CLAUDE_CODE_")
        }
    return env


def start_agent(
    profile: AgentProfile,
    *,
    prompt: str,
    cwd: Path,
    workspace: Path,
    env: Mapping[str, str] | None = None,
) -> AgentProcess:
    """Launch the selected coding agent in the background."""
    command = build_agent_command(profile, prompt)
    run_env = agent_env(profile, workspace, env)

    if profile.key == "claude":
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=run_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(prompt)
        proc.stdin.close()
    else:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    label = "cursor" if profile.key == "cursor" else "claude"
    activity = AgentActivityTracker() if profile.key == "cursor" else None
    return AgentProcess(label=label, command=command, proc=proc, activity=activity)
