# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the plugin's garak-venv preflight check and provisioning delegation."""

import subprocess
from pathlib import Path

import pytest
import typer
from nemo_iron_swarm_plugin.cli import checks, provisioning
from nemo_iron_swarm_plugin.config import GARAK_PYTHON_ENVVAR, IronSwarmConfig


def _config(tmp_path: Path) -> IronSwarmConfig:
    return IronSwarmConfig(venv_path=tmp_path / "venv", garak_venv_path=tmp_path / "garak-venv")


def test_run_checks_includes_garak_venv(tmp_path: Path) -> None:
    labels = [c.label for c in checks.run_checks(_config(tmp_path))]
    assert "iron-swarm venv" in labels
    assert "garak venv" in labels


def test_garak_venv_ok_reports_missing(tmp_path: Path) -> None:
    ok, detail = checks.garak_venv_ok(_config(tmp_path))
    assert ok is False
    assert "garak venv missing" in detail


def test_garak_venv_ok_reports_present(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.garak_python.parent.mkdir(parents=True)
    cfg.garak_python.touch()
    ok, _ = checks.garak_venv_ok(cfg)
    assert ok is True


def test_run_iron_swarm_setup_delegates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(tmp_path)
    recorded_cmd: list[str] = []
    recorded_env: dict[str, str] = {}

    def fake_run(cmd: list[str], action: str, env: dict[str, str] | None = None) -> None:
        recorded_cmd[:] = cmd
        recorded_env.update(env or {})
        cfg.garak_python.parent.mkdir(parents=True, exist_ok=True)
        cfg.garak_python.touch()  # simulate iron-swarm setup creating the venv

    monkeypatch.setattr(provisioning, "run_subprocess", fake_run)
    provisioning.run_iron_swarm_setup(cfg, force=False)

    assert recorded_cmd == [str(cfg.iron_swarm_bin), "setup"]
    assert recorded_env[GARAK_PYTHON_ENVVAR] == str(cfg.garak_python)


def test_run_iron_swarm_setup_force_passes_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(tmp_path)
    cfg.garak_python.parent.mkdir(parents=True)
    cfg.garak_python.touch()
    recorded: dict[str, object] = {}

    def fake_run(cmd: list[str], action: str, env: dict[str, str] | None = None) -> None:
        recorded["cmd"] = cmd

    monkeypatch.setattr(provisioning, "run_subprocess", fake_run)
    provisioning.run_iron_swarm_setup(cfg, force=True)
    assert recorded["cmd"] == [str(cfg.iron_swarm_bin), "setup", "--force"]


def test_run_iron_swarm_setup_runs_even_when_garak_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(tmp_path)
    cfg.garak_python.parent.mkdir(parents=True)
    cfg.garak_python.touch()  # garak already present, yet setup still runs to re-ensure the gateway
    called = False

    def fake_run(cmd: list[str], action: str, env: dict[str, str] | None = None) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(provisioning, "run_subprocess", fake_run)
    provisioning.run_iron_swarm_setup(cfg, force=False)
    assert called is True  # not gated on the garak venv — gateway is re-ensured every setup


# ── run_subprocess: streaming + timeout ──────────────────────────────────


def test_run_subprocess_streams_instead_of_capturing() -> None:
    """A captured multi-minute `uv pip install` shows no progress and reads as hung."""
    recorded: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        recorded.update(kwargs)
        return subprocess.CompletedProcess(cmd, returncode=0)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(provisioning.subprocess, "run", fake_run)
        provisioning.run_subprocess(["uv", "pip", "install", "iron-swarm"], "install iron-swarm")

    assert "capture_output" not in recorded and "stdout" not in recorded  # inherits the terminal
    assert recorded["timeout"] == provisioning.SUBPROCESS_TIMEOUT_SECONDS


def test_run_subprocess_exits_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=provisioning.SUBPROCESS_TIMEOUT_SECONDS)

    monkeypatch.setattr(provisioning.subprocess, "run", fake_run)
    with pytest.raises(typer.Exit) as excinfo:
        provisioning.run_subprocess(["uv", "pip", "install", "iron-swarm"], "install iron-swarm", timeout=1)
    assert excinfo.value.exit_code == 1


def test_run_subprocess_exits_on_nonzero_returncode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provisioning.subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, returncode=2))
    with pytest.raises(typer.Exit):
        provisioning.run_subprocess(["uv", "venv"], "create venv")
