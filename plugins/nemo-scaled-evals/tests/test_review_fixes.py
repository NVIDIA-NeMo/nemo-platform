# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cover correctness fixes identified during review."""

from __future__ import annotations

import asyncio
import io
import subprocess
import tarfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

try:
    import click
    import httpx
    from nemo_scaled_evals_plugin import migrations
    from scaled_evals.api.build import buildkit
    from scaled_evals.api.build.errors import BuildError
    from scaled_evals.cli.client import make_client, request
    from scaled_evals.dispatch.kubectl import execute_kubectl
except ImportError as exc:
    pytest.skip(f"scaled-evals plugin not installed: {exc}", allow_module_level=True)


class _MigrationResult:
    def fetchone(self) -> tuple[None]:
        return (None,)


class _MigrationConnection:
    def __init__(self) -> None:
        self.autocommit = True
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *_args: Any, **_kwargs: Any) -> _MigrationResult:
        return _MigrationResult()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_fresh_schema_is_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    schema_files = [Path("schema/00.sql"), Path("schema/01.sql")]
    migration_files = [Path("migrations/001.sql")]
    connection = _MigrationConnection()
    events: list[tuple[str, bool]] = []

    monkeypatch.setattr(migrations, "_connect", lambda *_args: nullcontext(connection))
    monkeypatch.setattr(migrations, "sql_root", lambda: Path("."))
    monkeypatch.setattr(
        migrations,
        "_sql_files",
        lambda path: migration_files if path.name == "migrations" else schema_files,
    )
    monkeypatch.setattr(
        migrations,
        "_run_file",
        lambda conn, path: events.append((path.as_posix(), conn.autocommit)),
    )

    assert migrations.apply_sql("unused") == (2, 1)
    assert events == [
        ("schema/00.sql", False),
        ("schema/01.sql", False),
        ("migrations/001.sql", True),
    ]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.autocommit is True

    connection = _MigrationConnection()
    monkeypatch.setattr(migrations, "_connect", lambda *_args: nullcontext(connection))

    def fail_second_schema(_conn: _MigrationConnection, path: Path) -> None:
        if path == schema_files[1]:
            raise RuntimeError("interrupted schema load")

    monkeypatch.setattr(migrations, "_run_file", fail_second_schema)
    with pytest.raises(RuntimeError, match="interrupted schema load"):
        migrations.apply_sql("unused")
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.autocommit is True


def test_external_commands_and_http_redirects_fail_bounded() -> None:
    runner_kwargs: dict[str, Any] = {}

    def timeout_runner(args: list[str], **kwargs: Any) -> None:
        runner_kwargs.update(kwargs)
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    result = execute_kubectl(["kubectl", "get", "pods"], runner=timeout_runner)
    assert runner_kwargs["timeout"] == 120.0
    assert result.returncode == 124
    assert result.stdout == ""
    assert "timed out" in result.stderr

    transport = httpx.MockTransport(
        lambda _request: httpx.Response(302, headers={"location": "https://example.invalid"})
    )
    with make_client("https://api.example.invalid", None, transport=transport) as client:
        with pytest.raises(click.ClickException, match="HTTP 302"):
            request(client, "GET", "/tasks")


def test_task_pack_extraction_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "pack.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in ("one", "two"):
            content = b"ab"
            member = tarfile.TarInfo(name)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))

    monkeypatch.setattr(buildkit.settings, "task_pack_max_members", 1)
    monkeypatch.setattr(buildkit.settings, "task_pack_max_extracted_size_bytes", 100)
    with pytest.raises(BuildError, match="member limit"):
        buildkit._extract_tarball(archive, tmp_path / "members")

    monkeypatch.setattr(buildkit.settings, "task_pack_max_members", 10)
    monkeypatch.setattr(buildkit.settings, "task_pack_max_extracted_size_bytes", 3)
    with pytest.raises(BuildError, match="extracted-size limit"):
        buildkit._extract_tarball(archive, tmp_path / "size")


async def test_buildkit_timeout_terminates_and_reaps_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _HangingProcess:
        returncode = None
        communicate_calls = 0
        terminated = False

        async def communicate(self) -> tuple[bytes, None]:
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                await asyncio.Future()
            return b"", None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            raise AssertionError("terminate should have been enough")

    process = _HangingProcess()

    async def create_process(*_args: Any, **_kwargs: Any) -> _HangingProcess:
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(buildkit, "_buildctl_args", lambda *_args: ["buildctl"])
    monkeypatch.setattr(buildkit, "_buildctl_env", lambda *_args: {})
    monkeypatch.setattr(buildkit.settings, "buildkit_timeout_seconds", 0.001)

    with pytest.raises(BuildError, match="timed out"):
        await buildkit._run_buildctl(
            tmp_path / "context",
            "registry.example.invalid/task:rev1",
            tmp_path / "metadata.json",
            tmp_path,
        )
    assert process.terminated is True
    assert process.communicate_calls == 2
