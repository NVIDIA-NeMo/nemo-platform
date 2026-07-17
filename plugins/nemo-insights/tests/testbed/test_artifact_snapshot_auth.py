# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for authenticated Intake snapshot exports."""

from pathlib import Path

import pytest
from testbed import artifact
from testbed.registry import Subject


def _glamr_subject(**overrides: object) -> Subject:
    return Subject(
        "glamr",
        "intake",
        {
            "agent": "glamr",
            "workspace": "default",
            "base_url": "https://agenthub.aire.nvidia.com",
            "auth": "basic",
            "intake_path_prefix": "/glamr/intake",
            "auth_user_env": "GLAMR_INTAKE_USER",
            "auth_password_env": "GLAMR_INTAKE_PASSWORD",
            **overrides,
        },
    )


def test_snapshot_basic_auth_client_uses_named_credentials_and_normalized_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GLAMR_INTAKE_USER", "intake-user")
    monkeypatch.setenv("GLAMR_INTAKE_PASSWORD", "secret")
    built: dict[str, object] = {}
    sentinel = object()

    def fake_builder(**kwargs: object) -> object:
        built.update(kwargs)
        return sentinel

    monkeypatch.setattr(artifact, "build_basic_auth_intake_client", fake_builder)

    client = artifact._basic_auth_intake_client_for([_glamr_subject()], "https://snapshot.example")

    assert client is sentinel
    assert built == {
        "base_url": "https://snapshot.example",
        "username": "intake-user",
        "password": "secret",
        "real_prefix": "/glamr/intake/",
    }


@pytest.mark.parametrize(
    ("missing_env", "credential"),
    [
        ("GLAMR_INTAKE_USER", "username"),
        ("GLAMR_INTAKE_PASSWORD", "password"),
    ],
)
def test_snapshot_basic_auth_client_exits_for_missing_credential(
    monkeypatch: pytest.MonkeyPatch,
    missing_env: str,
    credential: str,
) -> None:
    monkeypatch.setenv("GLAMR_INTAKE_USER", "intake-user")
    monkeypatch.setenv("GLAMR_INTAKE_PASSWORD", "secret")
    monkeypatch.delenv(missing_env)

    with pytest.raises(SystemExit, match=f"glamr.*{credential}.*{missing_env}"):
        artifact._basic_auth_intake_client_for([_glamr_subject()], "https://snapshot.example")


def test_snapshot_non_basic_subject_does_not_build_authenticated_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        artifact,
        "build_basic_auth_intake_client",
        lambda **kwargs: pytest.fail(f"unexpected basic-auth builder call: {kwargs}"),
    )

    assert (
        artifact._basic_auth_intake_client_for(
            [Subject("plain", "intake", {"workspace": "default", "base_url": "https://snapshot.example"})],
            "https://snapshot.example",
        )
        is None
    )


def test_snapshot_setup_failure_does_not_construct_authenticated_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    constructed = False

    def fake_client(subjects: list[Subject], source_url: str) -> object:
        nonlocal constructed
        constructed = True
        return object()

    def fail_pick_records(tmp_dir: Path, names: list[str]) -> list[Path]:
        raise RuntimeError("setup failed")

    monkeypatch.setattr(artifact, "_basic_auth_intake_client_for", fake_client)
    monkeypatch.setattr(artifact, "pick_records", fail_pick_records)

    with pytest.raises(RuntimeError, match="setup failed"):
        artifact.snapshot_export([_glamr_subject()], tmp_path / "snapshot.tar.zst", tmp_path / "tmp", since=None)

    assert not constructed


def test_snapshot_export_passes_authenticated_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sentinel = object()
    seen: dict[str, object] = {}
    monkeypatch.setattr(artifact, "_basic_auth_intake_client_for", lambda subjects, source_url: sentinel)
    monkeypatch.setattr(artifact, "fetch_platform_info", lambda source_url: None)

    def fake_export(base_url: str, workspaces: list[str], out_dir: Path, *, since: object, client: object) -> dict:
        seen.update(base_url=base_url, workspaces=workspaces, client=client)
        for workspace in workspaces:
            ws_dir = out_dir / "export" / workspace
            ws_dir.mkdir(parents=True)
            for name in ("spans.jsonl", "annotations.jsonl", "evaluator_results.jsonl"):
                (ws_dir / name).write_text("", encoding="utf-8")
        return {
            "workspaces": {
                workspace: {"spans": 0, "annotations": 0, "evaluator_results": 0} for workspace in workspaces
            },
            "min_start_time": None,
            "max_start_time": None,
        }

    monkeypatch.setattr(artifact.export, "export_workspaces", fake_export)
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()

    artifact.snapshot_export([_glamr_subject()], tmp_path / "snapshot.tar.zst", tmp_dir, since=None)

    assert seen["client"] is sentinel
