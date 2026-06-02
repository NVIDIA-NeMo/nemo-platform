# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``InMemoryRunnerBackend`` log/config layout and lifecycle.

Pin contracts that out-of-process callers (notably the ``nemo agents logs``
CLI) rely on:

- The log file path is deterministic (``<system_dir>/<name>.log``), exposed
  on ``DeploymentInfo.log_path``, and matches the path returned by
  ``log_path_for(name)`` — so the CLI can locate logs without round-trip
  through the API.
- Subprocess exit (``proc.poll() is not None``) is surfaced through
  ``get_deployment_status`` with the exit code in ``DeploymentInfo.error``,
  so the controller can mark deployments failed without waiting for the
  health-check timeout.
- The system dir lives under the configured ``workspace_dir`` (default:
  ``nmp_user_data_dir() / "agents"``), not the plugin source tree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from nemo_agents_plugin.config import AgentsConfig, ControllerConfig
from nemo_agents_plugin.runner.in_memory import InMemoryRunnerBackend, _resolve_nat_bin
from nmp.common.config import Configuration, nmp_user_data_dir


def _backend(workspace_dir: Path) -> InMemoryRunnerBackend:
    cfg = ControllerConfig(workspace_dir=workspace_dir)
    return InMemoryRunnerBackend(cfg)


# ---------------------------------------------------------------------------
# Default workspace_dir resolves through nmp_user_data_dir()
# ---------------------------------------------------------------------------


def test_default_workspace_dir_is_under_user_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default workspace_dir resolves to ``nmp_user_data_dir() / 'agents'``.

    Earlier versions defaulted to the plugin source root, which leaked
    runtime state into the source tree (and was undocumented).  Artifacts
    now route through the standard NMP user-data location so they survive
    ``/tmp/`` cleanup and live in a well-known place.
    """
    monkeypatch.setenv("NMP_DATA_DIR", str(tmp_path))
    Configuration.clear_cache()
    try:
        cfg = AgentsConfig.get()
        # workspace_dir is computed relative to the user-data root.
        assert cfg.controller.workspace_dir == nmp_user_data_dir() / "agents"
        assert cfg.controller.workspace_dir == tmp_path / "agents"
    finally:
        Configuration.clear_cache()


def test_workspace_dir_follows_xdg_data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``XDG_DATA_HOME`` shifts the workspace_dir alongside the rest of NMP state."""
    monkeypatch.delenv("NMP_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    Configuration.clear_cache()
    try:
        cfg = AgentsConfig.get()
        assert cfg.controller.workspace_dir == tmp_path / "nemo" / "agents"
    finally:
        Configuration.clear_cache()


def test_workspace_dir_passed_directly_to_controller_config(tmp_path: Path) -> None:
    """Constructing ``ControllerConfig`` with an explicit ``workspace_dir`` honours it."""
    custom = tmp_path / "custom"
    cfg = ControllerConfig(workspace_dir=custom)
    backend = InMemoryRunnerBackend(cfg)
    assert backend.output_base_dir == custom.resolve()
    assert backend.system_dir == custom.resolve() / "system"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_log_path_for_is_deterministic(tmp_path: Path) -> None:
    """``log_path_for`` returns ``<system_dir>/<name>.log`` — no random suffix."""
    backend = _backend(tmp_path)
    assert backend.log_path_for("react-agent-abcd1234") == tmp_path / "system" / "react-agent-abcd1234.log"


def test_log_path_and_config_path_share_basename(tmp_path: Path) -> None:
    """Config and log files share a deterministic basename so they pair up."""
    backend = _backend(tmp_path)
    name = "calc-1"
    assert backend.log_path_for(name).stem == backend.config_path_for(name).stem
    assert backend.log_path_for(name).suffix == ".log"
    assert backend.config_path_for(name).suffix == ".yaml"


def test_sanitize_name_strips_unsafe_chars(tmp_path: Path) -> None:
    """Pathological deployment names are coerced to a safe filename component."""
    backend = _backend(tmp_path)
    log = backend.log_path_for("../oops/../escape")
    # No path traversal: the result is a single child of system_dir.
    assert log.parent == backend.system_dir
    # Slashes are replaced (so the path can't escape system_dir).
    assert "/" not in log.name
    # And the resolved path is contained within system_dir.
    assert backend.system_dir in log.resolve().parents


def test_system_dir_is_under_workspace_dir(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    assert backend.system_dir == tmp_path / "system"
    assert backend.output_base_dir == tmp_path


# ---------------------------------------------------------------------------
# _write_config writes deterministically under system_dir
# ---------------------------------------------------------------------------


def test_write_config_uses_deterministic_path(tmp_path: Path) -> None:
    """Repeated writes target the same file (no random suffix)."""
    backend = _backend(tmp_path)
    config = {"workflow": {"_type": "react_agent"}}
    p1 = backend._write_config("calc", config)
    p2 = backend._write_config("calc", config)
    assert p1 == p2
    assert p1 == backend.config_path_for("calc")
    # Round-trip the YAML to confirm contents are correct.
    assert yaml.safe_load(p1.read_text()) == config


def test_write_config_creates_system_dir(tmp_path: Path) -> None:
    backend = _backend(tmp_path / "fresh")
    backend._write_config("calc", {"a": 1})
    assert (tmp_path / "fresh" / "system").is_dir()


# ---------------------------------------------------------------------------
# create_deployment populates DeploymentInfo.log_path and writes the log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_deployment_records_log_path(tmp_path: Path) -> None:
    """``DeploymentInfo.log_path`` is populated and matches ``log_path_for``."""
    backend = _backend(tmp_path)

    # Replace the spawn step with a no-op fake process that immediately
    # "starts" (poll returns None) so the test doesn't depend on ``nat``.
    class _FakeProc:
        pid = 4242
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

    fake = _FakeProc()

    def _fake_spawn(self_, name, config_path, log_path, port):  # noqa: ANN001
        # Touch the log file so callers can locate it — mirrors real spawn.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        return fake

    with patch.object(InMemoryRunnerBackend, "_spawn", _fake_spawn):
        info = await backend.create_deployment("calc-1", {"workflow": {}}, port=49200)

    assert info.log_path == str(backend.log_path_for("calc-1"))
    assert Path(info.log_path).exists()
    assert info.pid == 4242
    assert info.status == "starting"


# ---------------------------------------------------------------------------
# get_deployment_status surfaces subprocess exit code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_deployment_status_reports_dead_subprocess(tmp_path: Path) -> None:
    """A dead subprocess is reported as ``failed`` with the OS exit code.

    Without this contract the deployment could sit in ``starting`` until
    the health-check timeout elapsed; the controller relies on this to
    fail fast when the spawned process exits during startup.
    """
    backend = _backend(tmp_path)

    class _FakeProc:
        pid = 7777
        returncode = 1

        def poll(self) -> int | None:
            return 1  # always reports exited with code 1

    fake = _FakeProc()

    def _fake_spawn(self_, name, config_path, log_path, port):  # noqa: ANN001
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        return fake

    with patch.object(InMemoryRunnerBackend, "_spawn", _fake_spawn):
        info = await backend.create_deployment("calc-1", {}, port=49201)
    assert info.status == "starting"

    status = await backend.get_deployment_status("calc-1")
    assert status is not None
    assert status.status == "failed"
    assert "exited with code 1" in status.error


@pytest.mark.asyncio
async def test_get_deployment_status_alive_subprocess_unchanged(tmp_path: Path) -> None:
    """Backward behaviour: an alive process keeps its ``starting`` status."""
    backend = _backend(tmp_path)

    class _FakeProc:
        pid = 1111
        returncode: int | None = None

        def poll(self) -> int | None:
            return None

    fake = _FakeProc()

    def _fake_spawn(self_, name, config_path, log_path, port):  # noqa: ANN001
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")
        return fake

    with patch.object(InMemoryRunnerBackend, "_spawn", _fake_spawn):
        await backend.create_deployment("calc-1", {}, port=49202)

    status = await backend.get_deployment_status("calc-1")
    assert status is not None
    assert status.status == "starting"
    assert status.error == ""


# ---------------------------------------------------------------------------
# End-to-end: real subprocess that exits 1 — log path is reachable.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_subprocess_exit_writes_log_at_recorded_path(tmp_path: Path) -> None:
    """Spawn a real (trivial) subprocess and verify the log file is at the
    location recorded in ``DeploymentInfo.log_path``.

    Catches regressions where the log path advertised by the backend
    drifts from where the file is actually written — which would
    silently break the ``nemo agents logs`` post-mortem flow.
    """
    backend = _backend(tmp_path)

    # Patch _spawn to run a tiny python one-liner that prints and exits 1.
    def _spawn_python(self_, name, config_path, log_path, port):  # noqa: ANN001
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("w")
        try:
            return subprocess.Popen(
                [sys.executable, "-c", "import sys; print('agent boot failed'); sys.exit(1)"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_file.close()

    with patch.object(InMemoryRunnerBackend, "_spawn", _spawn_python):
        info = await backend.create_deployment("calc-1", {}, port=49203)

    # Wait briefly for the subprocess to exit.
    proc = backend._processes["calc-1"]
    proc.wait(timeout=10)

    log_path = Path(info.log_path)
    assert log_path == backend.log_path_for("calc-1")
    assert log_path.exists()
    assert "agent boot failed" in log_path.read_text()

    status = await backend.get_deployment_status("calc-1")
    assert status is not None
    assert status.status == "failed"
    assert "exited with code 1" in status.error


# ---------------------------------------------------------------------------
# _resolve_nat_bin: how the runner finds the `nat` executable.
#
# The runner spawns `nat start fastapi` per deployment.  Resolution must work
# under every supported install path (activated venv, agentic container,
# `uv tool install`, and explicit override) without requiring users to massage
# PATH themselves.
# ---------------------------------------------------------------------------


def test_resolve_nat_bin_uses_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """`shutil.which` is preferred — covers activated venvs and the container."""
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/local/bin/{name}")
    assert _resolve_nat_bin() == "/usr/local/bin/nat"


def test_resolve_nat_bin_uses_sibling_of_sys_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When `nat` is not on PATH, look next to `sys.executable`.

    This is the `uv tool install nemo-platform` case: the tool venv contains
    `nat` (it's co-installed with `nemo` via the `[services]` chain), but the
    venv's `bin/` is not prepended to PATH, so `shutil.which` returns None.
    """
    monkeypatch.setattr("shutil.which", lambda _: None)

    fake_venv_bin = tmp_path / "bin"
    fake_venv_bin.mkdir()
    fake_python = fake_venv_bin / "python"
    fake_python.touch()
    fake_nat = fake_venv_bin / "nat"
    fake_nat.write_text("#!/bin/sh\necho nat-stub\n")
    monkeypatch.setattr(sys, "executable", str(fake_python))

    assert _resolve_nat_bin() == str(fake_nat)


def test_resolve_nat_bin_falls_back_to_container_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When nothing else matches, return the container path. This preserves
    backwards-compatible behavior in the agentic container even if the PATH
    lookup somehow fails inside it."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    # sys.executable points somewhere with no sibling `nat`.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.touch()
    monkeypatch.setattr(sys, "executable", str(fake_python))

    assert _resolve_nat_bin() == "/app/.venv/bin/nat"
