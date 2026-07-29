# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Transfer tests for the Docker Compose sandbox provider."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.base import SandboxCreateError, SandboxStatus
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers import _compose_transfer as compose_transfer

from packages.nemo_evaluator_sdk.tests.agent_eval._compose_testkit import _compose_suffix, _create, _provider, _Runner

_FILE_PARENT_CREATED = "__NEMO_COMPOSE_FILE_PARENT_CREATED__"
_FILE_PARENT_OPERATION = "nemo-compose-file-parent"


def _assert_file_parent_operation(command: tuple[str, ...], parent: str) -> None:
    assert command[:7] == ("exec", "--no-TTY", "--user", "0", "agent", "sh", "-c")
    script, operation, parent_arg, identity = command[7:]
    assert operation == _FILE_PARENT_OPERATION
    assert parent_arg == parent
    assert identity == "1001:1002"
    assert parent not in script
    assert identity not in script
    assert 'chown -h "$identity" -- "$parent"' in script


@pytest.mark.parametrize(
    ("target", "directory", "message"),
    [
        ("", False, "Container path cannot be empty"),
        ("/", False, "File upload target cannot be the container root"),
        (".", False, "File upload target cannot be the container root"),
        ("work/", False, "File upload target must name an exact file"),
        ("/", True, "Directory upload target cannot be the container root"),
        (".", True, "Directory upload target cannot be the container root"),
    ],
)
def test_upload_target_validation_rejects_unsafe_paths(
    target: str,
    directory: bool,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        compose_transfer._normalized_upload_target(target, directory=directory)


def test_upload_target_validation_normalizes_once() -> None:
    assert (
        compose_transfer._normalized_upload_target(
            "ignored/../work/seed.txt",
            directory=False,
        )
        == "/work/seed.txt"
    )
    assert compose_transfer._normalized_upload_target("ignored/../work", directory=True) == "/work"


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
    assert transfer_suffixes[0] == (
        "exec",
        "--no-TTY",
        "agent",
        "sh",
        "-c",
        'printf "%s:%s" "$(id -u)" "$(id -g)"',
    )
    _assert_file_parent_operation(transfer_suffixes[1], "/missing/parent")
    assert transfer_suffixes[2:4] == [
        ("cp", str(source), "agent:/missing/parent/seed.txt"),
        (
            "exec",
            "--no-TTY",
            "--user",
            "0",
            "agent",
            "chown",
            "1001:1002",
            "--",
            "/missing/parent/seed.txt",
        ),
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
        ("exec", "--no-TTY", "--user", "0", "agent", "mkdir", "-p", "--", "/work/existing"),
        ("cp", f"{source}{os.sep}.", "agent:/work/existing"),
        ("exec", "--no-TTY", "agent", "sh", "-c", 'printf "%s:%s" "$(id -u)" "$(id -g)"'),
        ("exec", "--no-TTY", "--user", "0", "agent", "chown", "-R", "1001:1002", "--", "/work/existing"),
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
    assert suffixes[0] == (
        "exec",
        "--no-TTY",
        "agent",
        "sh",
        "-c",
        'printf "%s:%s" "$(id -u)" "$(id -g)"',
    )
    _assert_file_parent_operation(suffixes[1], "/missing/parent")
    assert suffixes[2:4] == [
        ("cp", str(source_file), "agent:/missing/parent/seed.txt"),
        (
            "exec",
            "--no-TTY",
            "--user",
            "0",
            "agent",
            "chown",
            "1001:1002",
            "--",
            "/missing/parent/seed.txt",
        ),
    ]
    assert ("cp", str(source_file), "agent:/root-seed.txt") in suffixes
    assert (
        "exec",
        "--no-TTY",
        "--user",
        "0",
        "agent",
        "chown",
        "1001:1002",
        "--",
        "/root-seed.txt",
    ) in suffixes
    assert ("exec", "--no-TTY", "--user", "0", "agent", "mkdir", "-p", "--", "/workspace") in suffixes
    assert ("cp", f"{source_dir}{os.sep}.", "agent:/workspace") in suffixes
    await provider.close(handle)


async def test_upload_file_derives_parent_from_normalized_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)

    await provider.upload_file(handle, source, "ignored/../root-seed.txt")

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert not any(args[-3:] == ("-p", "--", "/") for args in suffixes)
    assert ("cp", str(source), "agent:/root-seed.txt") in suffixes
    assert (
        "exec",
        "--no-TTY",
        "--user",
        "0",
        "agent",
        "chown",
        "1001:1002",
        "--",
        "/root-seed.txt",
    ) in suffixes
    await provider.close(handle)


async def test_upload_file_does_not_repair_a_preexisting_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    runner.directories.add("/existing/parent")
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)

    await provider.upload_file(handle, source, "/existing/parent/seed.txt")

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert suffixes[0] == (
        "exec",
        "--no-TTY",
        "agent",
        "sh",
        "-c",
        'printf "%s:%s" "$(id -u)" "$(id -g)"',
    )
    _assert_file_parent_operation(suffixes[1], "/existing/parent")
    assert suffixes[2:] == [
        ("cp", str(source), "agent:/existing/parent/seed.txt"),
        (
            "exec",
            "--no-TTY",
            "--user",
            "0",
            "agent",
            "chown",
            "1001:1002",
            "--",
            "/existing/parent/seed.txt",
        ),
    ]
    await provider.close(handle)


@pytest.mark.parametrize(
    ("return_code", "stdout", "stderr", "timed_out"),
    [
        (1, "", "token=sensitive-value", False),
        (2, "", "", False),
        (0, "", "", False),
        (0, "unexpected-parent-result", "", False),
        (0, f"{_FILE_PARENT_CREATED}\n", "", False),
        (0, _FILE_PARENT_CREATED, "token=sensitive-value", False),
        (0, _FILE_PARENT_CREATED, "", True),
    ],
)
async def test_upload_file_stops_after_unconfirmed_parent_preparation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    return_code: int,
    stdout: str,
    stderr: str,
    timed_out: bool,
) -> None:
    runner = _Runner()
    runner.parent_prepare_result = (return_code, stdout, stderr, timed_out)
    provider = _provider(tmp_path, environment_defaults={"TEST_TOKEN": "sensitive-value"})
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)

    with pytest.raises(RuntimeError, match="Compose upload target preparation failed") as caught:
        await provider.upload_file(handle, source, "/existing/parent/seed.txt")

    assert "sensitive-value" not in str(caught.value)
    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert suffixes[0] == (
        "exec",
        "--no-TTY",
        "agent",
        "sh",
        "-c",
        'printf "%s:%s" "$(id -u)" "$(id -g)"',
    )
    _assert_file_parent_operation(suffixes[1], "/existing/parent")
    assert len(suffixes) == 2
    await provider.close(handle)


async def test_upload_file_rejects_a_parent_replaced_during_preparation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    runner.parent_replaced_during_preparation = True
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)

    with pytest.raises(RuntimeError, match="Compose upload target preparation failed"):
        await provider.upload_file(handle, source, "/replaced/parent/seed.txt")

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert not any(args[:1] == ("cp",) for args in suffixes)
    assert not any(args[:6] == ("exec", "--no-TTY", "--user", "0", "agent", "chown") for args in suffixes)
    await provider.close(handle)


async def test_second_file_upload_treats_the_created_parent_as_existing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    first_source = tmp_path / "first.txt"
    first_source.write_text("first", encoding="utf-8")
    second_source = tmp_path / "second.txt"
    second_source.write_text("second", encoding="utf-8")
    transfer_start = len(runner.calls)

    await provider.upload_file(handle, first_source, "/shared/parent/first.txt")
    await provider.upload_file(handle, second_source, "/shared/parent/second.txt")

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    parent_operations = [
        args
        for args in suffixes
        if args[:7] == ("exec", "--no-TTY", "--user", "0", "agent", "sh", "-c") and args[-3] == _FILE_PARENT_OPERATION
    ]
    assert len(parent_operations) == 2
    assert runner.directories == {"/shared/parent"}
    assert runner.parent_ownership_repairs == [("/shared/parent", "1001:1002")]
    assert [args for args in suffixes if args[:6] == ("exec", "--no-TTY", "--user", "0", "agent", "chown")] == [
        (
            "exec",
            "--no-TTY",
            "--user",
            "0",
            "agent",
            "chown",
            "1001:1002",
            "--",
            "/shared/parent/first.txt",
        ),
        (
            "exec",
            "--no-TTY",
            "--user",
            "0",
            "agent",
            "chown",
            "1001:1002",
            "--",
            "/shared/parent/second.txt",
        ),
    ]
    await provider.close(handle)


async def test_upload_file_uses_non_login_shell_for_identity_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _Runner()
    provider = _provider(tmp_path)
    handle = await _create(monkeypatch, provider, runner)
    source = tmp_path / "seed.txt"
    source.write_text("seed", encoding="utf-8")
    transfer_start = len(runner.calls)

    await provider.upload_file(handle, source, "/seed.txt")

    suffixes = [
        _compose_suffix(argv) for argv, _, _ in runner.calls[transfer_start:] if argv[:2] == ("docker", "compose")
    ]
    assert ("exec", "--no-TTY", "agent", "sh", "-c", 'printf "%s:%s" "$(id -u)" "$(id -g)"') in suffixes
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
            assert suffixes[-1][:1] == ("cp",)
            assert not any(args[:6] == ("exec", "--no-TTY", "--user", "0", "agent", "chown") for args in suffixes)
        elif failure == "identity":
            assert not any(args[:1] == ("cp",) for args in suffixes)
            assert not any("chown" in args for args in suffixes)
    finally:
        runner.failures.clear()
        await provider.close(handle)
