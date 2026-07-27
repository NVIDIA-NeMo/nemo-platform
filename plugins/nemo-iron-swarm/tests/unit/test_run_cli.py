# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the `--benign-suite` wiring on the SDK `run` method and the CLI `run` command."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from _doubles import make_async_sdk, make_sdk
from typer.testing import CliRunner


def _write_suite(path: Path) -> Path:
    path.write_text("tool,payload,label,rationale,persona\nt,p,benign,r,pe\n", encoding="utf-8")
    return path


def test_sdk_run_uploads_benign_suite_into_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin import sdk as sdk_module

    captured: dict[str, Any] = {}

    class _Scheduler:
        def run_local(self, _job: Any, spec: dict, **kwargs: Any) -> dict:
            captured["spec"] = spec
            captured["kwargs"] = kwargs
            return {"status": "completed"}

    monkeypatch.setattr(sdk_module, "NemoJobScheduler", _Scheduler)
    monkeypatch.setattr(
        sdk_module, "upload_file_to_fileset", lambda _sdk, path, *, workspace: f"{workspace}/uploaded-{path.name}"
    )

    suite = _write_suite(tmp_path / "suite.csv")
    resource = sdk_module.IronSwarmPluginResource(make_sdk())
    resource.run(config="iron-swarm.yaml", benign_suite=str(suite), workspace="ws1")

    assert captured["spec"]["benign_suite_fileset"] == "ws1/uploaded-suite.csv"
    assert captured["kwargs"]["workspace"] == "ws1"


def test_sdk_run_without_benign_suite_omits_fileset(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin import sdk as sdk_module

    captured: dict[str, Any] = {}

    class _Scheduler:
        def run_local(self, _job: Any, spec: dict, **kwargs: Any) -> dict:
            captured["spec"] = spec
            return {"status": "completed"}

    monkeypatch.setattr(sdk_module, "NemoJobScheduler", _Scheduler)

    resource = sdk_module.IronSwarmPluginResource(make_sdk())
    resource.run(config="iron-swarm.yaml")

    assert "benign_suite_fileset" not in captured["spec"]


def test_async_sdk_run_builds_sync_client_and_uploads_benign_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nemo_iron_swarm_plugin import sdk as sdk_module

    captured: dict[str, Any] = {}
    sync_client = SimpleNamespace(name="sync-sdk")

    class _Scheduler:
        def run_local(self, _job: Any, spec: dict, **kwargs: Any) -> dict:
            captured["spec"] = spec
            captured["kwargs"] = kwargs
            return {"status": "completed"}

    def _fake_make_sdk(base: str) -> Any:
        captured["base"] = base
        return sync_client

    monkeypatch.setattr(sdk_module, "NemoJobScheduler", _Scheduler)
    monkeypatch.setattr(sdk_module, "make_sdk", _fake_make_sdk)
    monkeypatch.setattr(
        sdk_module, "upload_file_to_fileset", lambda sdk, path, *, workspace: f"{workspace}/uploaded-{path.name}"
    )

    suite = _write_suite(tmp_path / "suite.csv")
    async_platform = make_async_sdk(base_url="http://localhost:8080/")
    resource = sdk_module.AsyncIronSwarmPluginResource(async_platform)
    asyncio.run(resource.run(config="iron-swarm.yaml", benign_suite=str(suite), workspace="ws1"))

    assert captured["base"] == "http://localhost:8080/"  # sync client targets the async client's base URL
    assert captured["spec"]["benign_suite_fileset"] == "ws1/uploaded-suite.csv"
    assert captured["kwargs"]["workspace"] == "ws1"
    assert captured["kwargs"]["sdk"] is sync_client  # job runs against the sync client, not async_sdk


def _patch_cli(cli_main: Any, monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> Any:
    fake_sdk = SimpleNamespace(
        iron_swarm=SimpleNamespace(run=lambda **kwargs: captured.update(kwargs) or {"status": "completed"})
    )
    monkeypatch.setattr(cli_main.checks, "require_preflight", lambda _c: None)
    monkeypatch.setattr(cli_main, "make_sdk", lambda _u: fake_sdk)
    monkeypatch.setattr(cli_main, "base_url", lambda: "http://localhost:8080")
    monkeypatch.setattr(cli_main, "missing_secrets", lambda _p, env_files: [])
    monkeypatch.setattr(
        cli_main.IronSwarmConfig,
        "get",
        classmethod(lambda _cls: SimpleNamespace(default_workspace="default", operator_env_file=Path(".env"))),
    )
    return cli_main.IronSwarmCLI().get_cli()


def test_cli_run_forwards_benign_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.cli import main as cli_main

    config = tmp_path / "iron-swarm.yaml"
    config.write_text("agent: {}\n", encoding="utf-8")
    suite = _write_suite(tmp_path / "suite.csv")

    captured: dict[str, Any] = {}
    app = _patch_cli(cli_main, monkeypatch, captured)
    result = CliRunner().invoke(app, ["run", "--config", str(config), "--benign-suite", str(suite)])

    assert result.exit_code == 0, result.output
    assert captured["benign_suite"] == str(suite)


def test_cli_run_rejects_missing_benign_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_iron_swarm_plugin.cli import main as cli_main

    config = tmp_path / "iron-swarm.yaml"
    config.write_text("agent: {}\n", encoding="utf-8")

    captured: dict[str, Any] = {}
    app = _patch_cli(cli_main, monkeypatch, captured)
    result = CliRunner().invoke(app, ["run", "--config", str(config), "--benign-suite", str(tmp_path / "nope.csv")])

    assert result.exit_code == 1
    assert "not found" in result.output
    assert captured == {}  # bailed before invoking the SDK
