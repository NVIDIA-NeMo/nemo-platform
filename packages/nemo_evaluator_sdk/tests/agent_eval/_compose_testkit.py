# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared fakes and helpers for Docker Compose sandbox provider tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO, Any

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.base import SandboxSpec
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers import _compose_cli as compose_cli
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers.compose import (
    ComposeCommandResult,
    ComposeServiceTopology,
    DockerComposeSandboxProvider,
)

_TOPOLOGY = ComposeServiceTopology(
    target_service="agent",
    long_running_services=frozenset({"agent", "redis"}),
    one_shot_services=frozenset({"init"}),
)


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str], Path]] = []
        self.config: dict[str, Any] = {
            "services": {
                "agent": {},
                "redis": {},
                "init": {},
            }
        }
        self.config_stdout: str | None = None
        self.rows: list[dict[str, Any]] = [
            {"Service": "agent", "State": "running", "Health": "healthy", "ExitCode": 0},
            {"Service": "redis", "State": "running", "Health": "", "ExitCode": 0},
            {"Service": "init", "State": "exited", "Health": "", "ExitCode": 0},
        ]
        self.existing = False
        self.up_failure = False
        self.down_failures = 0
        self.failures: set[str] = set()
        self.directories: set[str] = set()
        self._down_attempts = 0

    async def __call__(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
        timeout: float,
        stdin: bytes | None,
        stream_output: IO[str] | None = None,
    ) -> ComposeCommandResult:
        del timeout, stdin
        self.calls.append((argv, dict(environment), cwd))
        if argv[:2] != ("docker", "compose"):
            return ComposeCommandResult(argv, 0, "", "")

        args = _compose_suffix(argv)
        if args[:3] == ("config", "--format", "json"):
            stdout = self.config_stdout if self.config_stdout is not None else json.dumps(self.config)
            return ComposeCommandResult(argv, 0, stdout, "")
        if args[:3] == ("ps", "--all", "--quiet"):
            return ComposeCommandResult(argv, 0, "existing\n" if self.existing else "", "")
        if args[:4] == ("ps", "--all", "--format", "json"):
            return ComposeCommandResult(argv, 0, json.dumps(self.rows), "")
        if args[:1] == ("up",):
            if stream_output is not None:
                stream_output.write("compose progress\n")
            if self.up_failure:
                return ComposeCommandResult(argv, 1, "", "missing image")
        if args[:1] == ("down",):
            self._down_attempts += 1
            if self._down_attempts <= self.down_failures:
                return ComposeCommandResult(argv, 1, "", "temporary failure")
        if args[:6] == ("exec", "--no-TTY", "--user", "0", "agent", "test"):
            return ComposeCommandResult(argv, int(args[-1] not in self.directories), "", "")
        if args[:1] == ("cp",) and "copy" in self.failures:
            return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'copy failed')}")
        if args[:1] == ("exec",) and "printf" in args[-1]:
            if "identity" in self.failures:
                return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'identity failed')}")
            return ComposeCommandResult(argv, 0, "1001:1002", "")
        if args[:6] == ("exec", "--no-TTY", "--user", "0", "agent", "mkdir") and "mkdir" in self.failures:
            return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'mkdir failed')}")
        if args[:6] == ("exec", "--no-TTY", "--user", "0", "agent", "chown") and "chown" in self.failures:
            return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'chown failed')}")
        return ComposeCommandResult(argv, 0, "", "")


def _files(tmp_path: Path, count: int = 1) -> tuple[Path, ...]:
    paths = tuple(tmp_path / f"compose-{index}.yaml" for index in range(count))
    for path in paths:
        path.write_text("services: {}\n", encoding="utf-8")
    return paths


def _provider(
    tmp_path: Path,
    *,
    files: tuple[Path, ...] | None = None,
    **kwargs: Any,
) -> DockerComposeSandboxProvider:
    lock_path = kwargs.pop("lock_path", tmp_path / "compose.lock")
    return DockerComposeSandboxProvider(
        compose_files=files or _files(tmp_path),
        service_topology=_TOPOLOGY,
        lock_path=lock_path,
        **kwargs,
    )


def _compose_suffix(argv: tuple[str, ...]) -> tuple[str, ...]:
    commands = {"config", "ps", "up", "down", "exec", "cp", "logs", "stop", "kill"}
    return argv[next(index for index, arg in enumerate(argv) if index > 1 and arg in commands) :]


async def _create(
    monkeypatch: pytest.MonkeyPatch,
    provider: DockerComposeSandboxProvider,
    runner: _Runner,
    spec: SandboxSpec | None = None,
):
    monkeypatch.setattr(compose_cli, "_run_command", runner)
    return await provider.create(spec or SandboxSpec())
