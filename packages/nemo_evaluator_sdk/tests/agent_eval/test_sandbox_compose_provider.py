# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hermetic lifecycle tests for the Docker Compose sandbox provider."""

from __future__ import annotations

import asyncio
import io
import json
import os
import select
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.base import (
    SandboxCreateError,
    SandboxSpec,
    SandboxStatus,
)
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers import compose
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers.compose import (
    ComposeCleanupError,
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
        if args[:1] == ("cp",) and "copy" in self.failures:
            return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'copy failed')}")
        if args[:1] == ("exec",) and "printf" in args[-1]:
            if "identity" in self.failures:
                return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'identity failed')}")
            return ComposeCommandResult(argv, 0, "1001:1002", "")
        if args[:6] == ("exec", "--no-tty", "--user", "0", "agent", "mkdir") and "mkdir" in self.failures:
            return ComposeCommandResult(argv, 1, "", f"token={environment.get('TEST_TOKEN', 'mkdir failed')}")
        if args[:6] == ("exec", "--no-tty", "--user", "0", "agent", "chown") and "chown" in self.failures:
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
    monkeypatch.setattr(compose, "_run_command", runner)
    return await provider.create(spec or SandboxSpec())


async def test_default_is_image_first_and_build_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    files = _files(tmp_path, count=2)
    project_dir = tmp_path / "workspace"
    project_dir.mkdir()
    provider = _provider(
        tmp_path,
        files=files,
        project_directory=project_dir,
        profiles=("gpu", "tools"),
    )

    handle = await _create(monkeypatch, provider, runner)
    up_argv, _environment, cwd = next(call for call in runner.calls if _compose_suffix(call[0])[:1] == ("up",))
    assert cwd == project_dir
    assert up_argv.count("--file") == 2
    assert [str(path) for path in files] == [up_argv[index + 1] for index, arg in enumerate(up_argv) if arg == "--file"]
    assert ["gpu", "tools"] == [up_argv[index + 1] for index, arg in enumerate(up_argv) if arg == "--profile"]
    assert "--project-directory" in up_argv
    assert "--no-build" in up_argv
    assert "--build" not in up_argv
    assert _compose_suffix(up_argv)[-2:] == ("--pull", "missing")
    assert handle.sandbox_id.startswith("nemo-eval-")

    await provider.close(handle)
    await provider.aclose()


@pytest.mark.parametrize(
    ("build", "pull_policy", "expected"),
    [
        (True, "always", "--build"),
        (True, "never", "--build"),
        (False, "always", "--no-build"),
        (False, "never", "--no-build"),
    ],
)
async def test_build_and_pull_policy_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    build: bool,
    pull_policy: str,
    expected: str,
) -> None:
    runner = _Runner()
    provider = _provider(
        tmp_path,
        project_name=f"matrix-{str(build).lower()}-{pull_policy}",
        build=build,
        pull_policy=pull_policy,
    )
    handle = await _create(monkeypatch, provider, runner)
    up = next(_compose_suffix(argv) for argv, _, _ in runner.calls if _compose_suffix(argv)[:1] == ("up",))
    assert expected in up
    assert up[-2:] == ("--pull", pull_policy)
    await provider.close(handle)


async def test_missing_image_does_not_fall_back_to_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    runner.up_failure = True
    provider = _provider(tmp_path)

    with pytest.raises(SandboxCreateError, match="missing image"):
        await _create(monkeypatch, provider, runner)

    suffixes = [_compose_suffix(argv) for argv, _, _ in runner.calls if argv[:2] == ("docker", "compose")]
    up = next(args for args in suffixes if args[:1] == ("up",))
    assert "--no-build" in up
    assert not any(args[:1] == ("build",) for args in suffixes)
    assert any(args[:1] == ("down",) for args in suffixes)


async def test_preflight_rejects_mismatched_topology_before_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    runner.config["services"]["unexpected"] = {}
    provider = _provider(tmp_path)

    with pytest.raises(SandboxCreateError, match="unexpected=.*unexpected"):
        await _create(monkeypatch, provider, runner)
    assert not any(_compose_suffix(argv)[:1] == ("up",) for argv, _, _ in runner.calls)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            [
                {"Service": "agent", "State": "running", "Health": "unhealthy"},
                {"Service": "redis", "State": "running", "Health": ""},
                {"Service": "init", "State": "exited", "ExitCode": 0},
            ],
            "not healthy",
        ),
        (
            [
                {"Service": "agent", "State": "running", "Health": "healthy"},
                {"Service": "redis", "State": "running", "Health": ""},
                {"Service": "init", "State": "exited", "ExitCode": 1},
            ],
            "did not exit successfully",
        ),
    ],
)
async def test_readiness_enforces_service_roles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rows: list[dict[str, Any]],
    message: str,
) -> None:
    runner = _Runner()
    runner.rows = rows
    provider = _provider(tmp_path)

    with pytest.raises(SandboxCreateError, match=message):
        await _create(monkeypatch, provider, runner)
    assert any(_compose_suffix(argv)[:1] == ("down",) for argv, _, _ in runner.calls)


@pytest.mark.parametrize("reverse_rows", [False, True])
def test_readiness_checks_every_scaled_service_replica(reverse_rows: bool) -> None:
    topology = ComposeServiceTopology(
        target_service="agent",
        long_running_services=frozenset({"agent"}),
        one_shot_services=frozenset({"init"}),
    )
    healthy_agent = {"Service": "agent", "State": "running", "Health": "healthy"}
    failed_agent = {"Service": "agent", "State": "exited", "Health": "", "ExitCode": 1}
    successful_init = {"Service": "init", "State": "exited", "ExitCode": 0}
    rows = [healthy_agent, failed_agent, successful_init]
    if reverse_rows:
        rows.reverse()

    problem = compose._services_ready(rows, topology)

    assert problem is not None
    assert "agent" in problem
    assert "not running" in problem


def test_readiness_checks_every_scaled_one_shot_replica() -> None:
    topology = ComposeServiceTopology(
        target_service="agent",
        long_running_services=frozenset({"agent"}),
        one_shot_services=frozenset({"init"}),
    )
    rows = [
        {"Service": "agent", "State": "running", "Health": "healthy"},
        {"Service": "init", "State": "exited", "ExitCode": 0},
        {"Service": "init", "State": "exited", "ExitCode": 1},
    ]

    assert compose._services_ready(rows, topology) == "Compose one-shot service 'init' did not exit successfully"


async def test_provider_options_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    monkeypatch.setattr(compose, "_run_command", runner)

    with pytest.raises(SandboxCreateError, match="provider_options"):
        await provider.create(SandboxSpec(provider_options={"build": True}))
    assert runner.calls == []


async def test_port_conflict_uses_caller_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    runner.config["services"]["agent"] = {
        "ports": [
            {
                "host_ip": "127.0.0.1",
                "published": "18080",
                "target": 8080,
                "protocol": "tcp",
            }
        ]
    }
    monkeypatch.setattr(compose, "_published_port_available", lambda _port: False)
    provider = _provider(tmp_path, port_override_hints={"agent": "AGENT_PORT"})

    with pytest.raises(SandboxCreateError, match="AGENT_PORT") as caught:
        await _create(monkeypatch, provider, runner)
    assert "127.0.0.1:18080 -> 8080/tcp" in str(caught.value)


async def test_preflight_parses_rendered_config_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    monkeypatch.setattr(compose, "_run_command", runner)
    original_loads = json.loads
    payloads: list[str] = []

    def tracked_loads(text: str) -> Any:
        payloads.append(text)
        return original_loads(text)

    monkeypatch.setattr(compose.json, "loads", tracked_loads)

    await provider._preflight(dict(os.environ))

    assert payloads == [json.dumps(runner.config)]


@pytest.mark.parametrize(
    ("config_stdout", "cause_type"),
    [
        ("{", json.JSONDecodeError),
        ("[]", TypeError),
        ('{"services": []}', TypeError),
    ],
)
async def test_invalid_rendered_config_preserves_create_error_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_stdout: str,
    cause_type: type[Exception],
) -> None:
    runner = _Runner()
    runner.config_stdout = config_stdout
    provider = _provider(tmp_path)

    with pytest.raises(SandboxCreateError, match="Could not inspect rendered Compose configuration") as caught:
        await _create(monkeypatch, provider, runner)

    assert isinstance(caught.value.__cause__, cause_type)


async def test_environment_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    monkeypatch.setenv("PORT", "from-host")
    provider = _provider(tmp_path, environment_defaults={"PORT": "default", "ONLY_DEFAULT": "yes"})
    handle = await _create(
        monkeypatch,
        provider,
        runner,
        SandboxSpec(env={"PORT": "from-spec"}),
    )

    up_environment = next(env for argv, env, _ in runner.calls if _compose_suffix(argv)[:1] == ("up",))
    assert up_environment["PORT"] == "from-spec"
    assert up_environment["ONLY_DEFAULT"] == "yes"
    await provider.close(handle)


async def test_teardown_hook_is_constrained_and_runs_before_down(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    events: list[str] = []

    async def hook(context) -> None:
        assert await context.service_is_running("agent")
        events.append("hook")
        stopped = await context.stop_service("agent")
        assert stopped.ok
        result = await context.exec_service("redis", ("redis-cli", "PING"))
        assert result.ok

    provider = _provider(tmp_path, teardown_hook=hook)
    handle = await _create(monkeypatch, provider, runner)
    await provider.close(handle)

    suffixes = [_compose_suffix(argv) for argv, _, _ in runner.calls if argv[:2] == ("docker", "compose")]
    assert events == ["hook"]
    assert next(i for i, args in enumerate(suffixes) if args[:1] == ("stop",)) < next(
        i for i, args in enumerate(suffixes) if args[:1] == ("down",)
    )


async def test_hook_failure_is_reported_but_down_still_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()

    async def hook(_context) -> None:
        raise RuntimeError("wipe failed")

    provider = _provider(tmp_path, teardown_hook=hook)
    handle = await _create(monkeypatch, provider, runner)
    with pytest.raises(ComposeCleanupError, match="wipe failed"):
        await provider.close(handle)
    assert any(_compose_suffix(argv)[:1] == ("down",) for argv, _, _ in runner.calls)


async def test_cancelled_close_finishes_down_then_restores_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hook(_context) -> None:
        entered.set()
        await release.wait()

    provider = _provider(tmp_path, teardown_hook=hook)
    handle = await _create(monkeypatch, provider, runner)
    close_task = asyncio.create_task(provider.close(handle))
    await entered.wait()
    close_task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await close_task
    assert any(_compose_suffix(argv)[:1] == ("down",) for argv, _, _ in runner.calls)


async def test_cancelled_startup_diagnostics_finishes_cleanup_before_restoring_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    runner.up_failure = True
    provider = _provider(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def capture_diagnostics(
        _environment: Mapping[str, str],
        *,
        reason: str,
    ) -> None:
        assert reason in {"startup-failure", "shutdown"}
        entered.set()
        await release.wait()

    monkeypatch.setattr(compose, "_run_command", runner)
    monkeypatch.setattr(provider, "_capture_diagnostics", capture_diagnostics)
    create_task = asyncio.create_task(provider.create(SandboxSpec()))
    await entered.wait()
    create_task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await create_task

    assert any(_compose_suffix(argv)[:1] == ("down",) for argv, _, _ in runner.calls)
    assert provider._session is None
    recovered_lock = compose._ComposeProjectLock.acquire(provider.lock_path)
    recovered_lock.release()


@pytest.mark.parametrize(("remove_volumes", "expected"), [(False, False), (True, True)])
async def test_volume_removal_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    remove_volumes: bool,
    expected: bool,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path, remove_project_volumes=remove_volumes)
    handle = await _create(monkeypatch, provider, runner)
    await provider.close(handle)
    down = next(_compose_suffix(argv) for argv, _, _ in runner.calls if _compose_suffix(argv)[:1] == ("down",))
    assert ("--volumes" in down) is expected


@pytest.mark.parametrize(
    ("remove_volumes", "expected_kinds", "expected_errors"),
    [
        (
            False,
            ["container", "network"],
            [
                "Managed Compose containers remain after teardown: container-a",
                "network query failed",
            ],
        ),
        (
            True,
            ["container", "network", "volume"],
            [
                "Managed Compose containers remain after teardown: container-a",
                "network query failed",
                "Managed Compose volumes remain after teardown: volume-a",
            ],
        ),
    ],
)
async def test_project_destruction_verification_preserves_kind_and_error_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    remove_volumes: bool,
    expected_kinds: list[str],
    expected_errors: list[str],
) -> None:
    provider = _provider(tmp_path, remove_project_volumes=remove_volumes)
    calls: list[str] = []
    responses = {
        "container": (["container-a"], None),
        "network": ([], "network query failed"),
        "volume": (["volume-a"], None),
    }

    async def managed_resource_names(
        kind: str,
        _environment: Mapping[str, str],
    ) -> tuple[list[str], str | None]:
        calls.append(kind)
        return responses[kind]

    monkeypatch.setattr(provider, "_managed_resource_names", managed_resource_names)

    errors = await provider._verify_project_destroyed(os.environ)

    assert calls == expected_kinds
    assert errors == expected_errors


async def test_project_destruction_verification_stops_after_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _provider(tmp_path, remove_project_volumes=True)
    calls: list[str] = []

    async def managed_resource_names(
        kind: str,
        _environment: Mapping[str, str],
    ) -> tuple[list[str], str | None]:
        calls.append(kind)
        if kind == "network":
            raise OSError("inspection failed")
        return [], None

    monkeypatch.setattr(provider, "_managed_resource_names", managed_resource_names)

    with pytest.raises(OSError, match="inspection failed"):
        await provider._verify_project_destroyed(os.environ)

    assert calls == ["container", "network"]


async def test_exec_transfer_and_status_target_configured_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)

    result = await provider.exec(handle, "echo ok", cwd="/work", env={"A": "b"}, stdin=b"x")
    assert result.ok
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)
    await provider.upload_file(handle, source, "/missing/parent/seed.txt")
    await provider.download_file(handle, "/work/out.txt", tmp_path / "out" / "out.txt")
    assert await provider.status(handle) == SandboxStatus.RUNNING

    suffixes = [_compose_suffix(argv) for argv, _, _ in runner.calls if argv[:2] == ("docker", "compose")]
    assert any(args[-4:] == ("agent", "sh", "-lc", "echo ok") for args in suffixes)
    transfer_suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert transfer_suffixes[:4] == [
        ("exec", "--no-tty", "--user", "0", "agent", "mkdir", "-p", "--", "/missing/parent"),
        ("cp", str(source), "agent:/missing/parent/seed.txt"),
        ("exec", "--no-tty", "agent", "sh", "-lc", 'printf "%s:%s" "$(id -u)" "$(id -g)"'),
        ("exec", "--no-tty", "--user", "0", "agent", "chown", "-R", "1001:1002", "--", "/missing/parent/seed.txt"),
    ]
    await provider.close(handle)


async def test_directory_transfers_copy_contents_into_prepared_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "source"
    source.mkdir()
    (source / "seed.txt").write_text("seed", encoding="utf-8")
    existing_download = tmp_path / "existing-download"
    existing_download.mkdir()
    absent_download = tmp_path / "absent" / "download"

    transfer_start = len(runner.calls)
    await provider.upload_dir(handle, source, "/work/existing")
    await provider.download_dir(handle, "/out", existing_download)
    await provider.download_dir(handle, "/out", absent_download)

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert suffixes[:4] == [
        ("exec", "--no-tty", "--user", "0", "agent", "mkdir", "-p", "--", "/work/existing"),
        ("cp", f"{source}{os.sep}.", "agent:/work/existing"),
        ("exec", "--no-tty", "agent", "sh", "-lc", 'printf "%s:%s" "$(id -u)" "$(id -g)"'),
        ("exec", "--no-tty", "--user", "0", "agent", "chown", "-R", "1001:1002", "--", "/work/existing"),
    ]
    assert ("cp", "agent:/out/.", str(existing_download)) in suffixes
    assert ("cp", "agent:/out/.", str(absent_download)) in suffixes
    assert existing_download.is_dir()
    assert absent_download.is_dir()
    await provider.close(handle)


async def test_relative_upload_targets_use_the_same_root_for_every_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    source_file = tmp_path / "seed.txt"
    source_file.write_text("seed", encoding="utf-8")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "nested.txt").write_text("nested", encoding="utf-8")

    transfer_start = len(runner.calls)
    await provider.upload_file(handle, source_file, "missing/parent/seed.txt")
    await provider.upload_file(handle, source_file, "root-seed.txt")
    await provider.upload_dir(handle, source_dir, "workspace")

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert suffixes[:4] == [
        ("exec", "--no-tty", "--user", "0", "agent", "mkdir", "-p", "--", "/missing/parent"),
        ("cp", str(source_file), "agent:/missing/parent/seed.txt"),
        ("exec", "--no-tty", "agent", "sh", "-lc", 'printf "%s:%s" "$(id -u)" "$(id -g)"'),
        (
            "exec",
            "--no-tty",
            "--user",
            "0",
            "agent",
            "chown",
            "-R",
            "1001:1002",
            "--",
            "/missing/parent/seed.txt",
        ),
    ]
    assert ("cp", str(source_file), "agent:/root-seed.txt") in suffixes
    assert (
        "exec",
        "--no-tty",
        "--user",
        "0",
        "agent",
        "chown",
        "-R",
        "1001:1002",
        "--",
        "/root-seed.txt",
    ) in suffixes
    assert ("exec", "--no-tty", "--user", "0", "agent", "mkdir", "-p", "--", "/workspace") in suffixes
    assert ("cp", f"{source_dir}{os.sep}.", "agent:/workspace") in suffixes
    await provider.close(handle)


@pytest.mark.parametrize(
    ("failure", "exception_type", "message"),
    [
        ("mkdir", RuntimeError, "Compose upload target preparation failed"),
        ("copy", RuntimeError, "Compose upload failed"),
        ("identity", SandboxCreateError, "Could not determine target service identity"),
        ("chown", RuntimeError, "Compose upload ownership repair failed"),
    ],
)
async def test_upload_failures_are_ordered_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    exception_type: type[Exception],
    message: str,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path, environment_defaults={"TEST_TOKEN": "sensitive-value"})
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)
    runner.failures.add(failure)

    try:
        with pytest.raises(exception_type, match=message) as caught:
            await provider.upload_file(handle, source, "/missing/parent/seed.txt")
        assert "sensitive-value" not in str(caught.value)
        suffixes = [
            _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
        ]
        if failure == "mkdir":
            assert not any(args[:1] == ("cp",) for args in suffixes)
        elif failure == "copy":
            assert not any("printf" in args[-1] or "chown" in args for args in suffixes if args[:1] == ("exec",))
        elif failure == "identity":
            assert not any("chown" in args for args in suffixes)
    finally:
        runner.failures.clear()
        await provider.close(handle)


async def test_closed_handle_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    await provider.close(handle)

    with pytest.raises(ValueError, match="not the active Compose session"):
        await provider.exec(handle, "true")


async def test_stale_handle_cannot_alias_recreated_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    first = await _create(monkeypatch, provider, runner, SandboxSpec(env={"SESSION": "first"}))
    await provider.close(first)
    second = await provider.create(SandboxSpec(env={"SESSION": "second"}))

    try:
        assert first.sandbox_id != second.sandbox_id
        with pytest.raises(ValueError, match="not the active Compose session"):
            await provider.close(first)
        assert await provider.status(second) == SandboxStatus.RUNNING
    finally:
        await provider.close(second)


async def test_active_session_freezes_project_scope_and_target_topology(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path, project_name="original", profiles=("original-profile",))
    handle = await _create(monkeypatch, provider, runner)
    original_scope = provider._command_scope()
    replacement_directory = tmp_path / "replacement"
    replacement_directory.mkdir()
    replacement_file = replacement_directory / "compose.yaml"
    replacement_file.write_text("services: {}\n", encoding="utf-8")

    provider.docker_bin = "replacement-docker"
    provider.project_directory = replacement_directory
    provider.compose_files = (replacement_file,)
    provider.project_name = "replacement"
    provider.profiles = ("replacement-profile",)
    provider.target_service = "replacement-service"
    provider.service_topology = ComposeServiceTopology(
        target_service="replacement-service",
        long_running_services=frozenset({"replacement-service"}),
    )

    assert provider._command_scope() == original_scope
    assert await provider.status(handle) == SandboxStatus.RUNNING
    await provider.exec(handle, "true")
    await provider.close(handle)

    compose_calls = [(argv, cwd) for argv, _, cwd in runner.calls if argv[:2] == ("docker", "compose")]
    assert compose_calls
    assert all(argv[argv.index("--project-name") + 1] == "original" for argv, _ in compose_calls)
    assert all(argv[0] == "docker" and cwd == tmp_path for argv, cwd in compose_calls)
    assert any(_compose_suffix(argv)[-4:] == ("agent", "sh", "-lc", "true") for argv, _ in compose_calls)
    assert provider._command_scope().project_name == "replacement"
    assert provider._command_scope().docker_bin == "replacement-docker"


def test_project_lock_and_generated_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    closed_fds: list[int] = []
    close_fd = os.close

    def record_close(fd: int) -> None:
        closed_fds.append(fd)
        close_fd(fd)

    monkeypatch.setattr(compose.os, "close", record_close)
    first = _provider(tmp_path, project_name="shared")
    second = _provider(tmp_path, project_name="shared")
    first_lock = compose._ComposeProjectLock.acquire(first.lock_path)
    try:
        with pytest.raises(SandboxCreateError, match="Another Compose sandbox"):
            compose._ComposeProjectLock.acquire(second.lock_path)
        assert len(closed_fds) == 1
    finally:
        first_lock.release()
    assert first_lock.fd is None

    second_lock = compose._ComposeProjectLock.acquire(second.lock_path)
    second_lock.release()
    assert second_lock.fd is None
    assert len(closed_fds) == 3

    generated = _provider(tmp_path, lock_path=tmp_path / "other.lock")
    assert generated.project_name.startswith("nemo-eval-")
    assert generated.project_name != first.project_name


async def test_create_wraps_lock_filesystem_errors(
    tmp_path: Path,
) -> None:
    lock_directory = tmp_path / "lock-directory"
    lock_directory.mkdir()
    provider = _provider(tmp_path, lock_path=lock_directory)

    with pytest.raises(SandboxCreateError, match="Could not acquire Compose project lock") as caught:
        await provider.create(SandboxSpec())

    assert isinstance(caught.value.__cause__, IsADirectoryError)
    assert provider._session is None


def test_project_lock_excludes_another_process(tmp_path: Path) -> None:
    lock_path = tmp_path / "compose.lock"
    script = "\n".join(
        [
            "import fcntl",
            "import os",
            "import sys",
            "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)",
            "fcntl.flock(fd, fcntl.LOCK_EX)",
            "print('locked', flush=True)",
            "sys.stdin.read(1)",
        ]
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 5)
        assert ready, "lock holder did not become ready"
        assert process.stdout.readline().strip() == "locked"

        with pytest.raises(SandboxCreateError, match="Another Compose sandbox"):
            compose._ComposeProjectLock.acquire(lock_path)
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
    assert process.returncode == 0

    contender_lock = compose._ComposeProjectLock.acquire(lock_path)
    contender_lock.release()
    assert contender_lock.fd is None


def test_invalid_configuration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        DockerComposeSandboxProvider(compose_files=(), service_topology=_TOPOLOGY)
    with pytest.raises(ValueError, match="pull_policy"):
        _provider(tmp_path, pull_policy="sometimes")
    with pytest.raises(ValueError, match="target_service"):
        ComposeServiceTopology(
            target_service="agent",
            long_running_services=frozenset({"redis"}),
        )


@pytest.mark.parametrize("project_name", ["a", "0", "a-b", "a_b", "a0-b_1"])
def test_valid_project_names_are_accepted(tmp_path: Path, project_name: str) -> None:
    assert _provider(tmp_path, project_name=project_name).project_name == project_name


@pytest.mark.parametrize("project_name", ["foo.bar", "Upper", "bad/name"])
def test_invalid_project_names_are_rejected(tmp_path: Path, project_name: str) -> None:
    with pytest.raises(ValueError, match="project_name"):
        _provider(tmp_path, project_name=project_name)


def test_redaction_covers_environment_and_inline_secrets() -> None:
    redacted = compose._redact(
        "TOKEN=secret-value\nAuthorization: Bearer bearer-value\npassword=hunter2",
        {**os.environ, "TOKEN": "secret-value"},
    )
    assert "secret-value" not in redacted
    assert "bearer-value" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("<redacted>") == 3


async def test_streaming_command_redacts_output_and_retains_raw_result(
    tmp_path: Path,
) -> None:
    environment = {**os.environ, "TEST_TOKEN": "stream-secret"}
    progress = io.StringIO()
    script = "\n".join(
        [
            "import sys",
            'print("token=stream-secret")',
            'print("password=hunter2", file=sys.stderr)',
        ]
    )

    result = await compose._run_command(
        (sys.executable, "-c", script),
        cwd=tmp_path,
        environment=environment,
        timeout=5,
        stdin=None,
        stream_output=progress,
    )

    assert result.ok
    assert result.stdout == "token=stream-secret\n"
    assert result.stderr == "password=hunter2\n"
    assert "stream-secret" not in progress.getvalue()
    assert "hunter2" not in progress.getvalue()
    assert progress.getvalue().count("<redacted>") == 2


async def test_streaming_timeout_retains_partial_output(tmp_path: Path) -> None:
    progress = io.StringIO()
    script = 'import time; print("started", flush=True); time.sleep(30)'

    result = await compose._run_command(
        (sys.executable, "-c", script),
        cwd=tmp_path,
        environment=os.environ,
        timeout=0.1,
        stdin=None,
        stream_output=progress,
    )

    assert result.timed_out
    assert result.stdout == "started\n"
    assert "timed out after 0.1s" in result.stderr.lower()
    assert progress.getvalue() == "started\n"


async def test_streaming_cancellation_terminates_process(tmp_path: Path) -> None:
    progress = io.StringIO()
    script = 'import time; print("started", flush=True); time.sleep(30)'
    task = asyncio.create_task(
        compose._run_command(
            (sys.executable, "-c", script),
            cwd=tmp_path,
            environment=os.environ,
            timeout=60,
            stdin=None,
            stream_output=progress,
        )
    )
    await asyncio.sleep(0.1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert progress.getvalue() == "started\n"
