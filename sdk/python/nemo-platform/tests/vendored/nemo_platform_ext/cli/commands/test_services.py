# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI-level tests for ``nemo services`` commands.

Tests use the Typer CliRunner with mocked process internals.  The ``base_dir``
fixture + ``_NMP_STATE_DIR`` env var ensure all state goes to a temp directory.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from types import ModuleType
from unittest.mock import ANY, MagicMock, patch

import pytest
from nemo_platform.cli.app import app
from nemo_platform.cli.commands.services._process import (
    ForegroundInstanceError,
    InstanceDescriptor,
    StopResult,
    acquire_lock,
    instance_dir,
    read_descriptor,
    write_descriptor,
)
from typer.testing import CliRunner

runner = CliRunner()

_PROCESS_MODULE = "nemo_platform.cli.commands.services._process"
_CLI_MODULE = "nemo_platform.cli.commands.services.cli"


_original_find_spec = __import__("importlib").util.find_spec


def _no_pyleak(name, *a, **kw):
    """Mock find_spec that hides ``pyleak`` while passing everything else through."""
    if name == "pyleak":
        return None
    return _original_find_spec(name, *a, **kw)


@pytest.fixture()
def base_dir(tmp_path: Path, monkeypatch) -> Path:
    d = tmp_path / "state" / "nmp"
    monkeypatch.setenv("_NMP_STATE_DIR", str(d))
    return d


# ---------------------------------------------------------------------------
# Group-level help
# ---------------------------------------------------------------------------


def test_services_group_is_registered():
    result = runner.invoke(app, ["services", "--help"])
    assert result.exit_code == 0
    assert "Run platform services locally." in result.stdout
    assert "run" in result.stdout


def test_services_help_lists_all_commands():
    result = runner.invoke(app, ["services", "--help"])
    assert result.exit_code == 0
    for cmd in ("run", "start", "stop", "restart", "status", "ls", "logs"):
        assert cmd in result.stdout, f"'{cmd}' not in help output"


# ---------------------------------------------------------------------------
# run (foreground)
# ---------------------------------------------------------------------------


def test_run_shows_services_extra_hint_when_pyleak_missing():
    with patch(f"{_CLI_MODULE}.importlib.util.find_spec", side_effect=_no_pyleak):
        result = runner.invoke(app, ["services", "run"])
    assert result.exit_code == 1
    assert "nemo-platform[all]" in result.stderr


def test_run_invokes_runner(base_dir: Path):
    mock_module = ModuleType("nmp.platform_runner.run")
    mock_run_platform = MagicMock()
    mock_module.run_platform = mock_run_platform

    with (
        patch.dict("sys.modules", {"nmp.platform_runner.run": mock_module}),
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_PROCESS_MODULE}.get_create_time", return_value=1000.0),
    ):
        result = runner.invoke(
            app,
            [
                "services",
                "run",
                "--services",
                "auth,entities",
                "--controllers",
                "jobs,models",
                "--host",
                "127.0.0.1",
                "--port",
                "9000",
                "--instance",
                "test-run",
            ],
        )

    assert result.exit_code == 0, result.stderr
    mock_run_platform.assert_called_once_with(
        services=["auth", "entities"],
        service_group=None,
        controllers=["jobs", "models"],
        controller_group=None,
        sidecars=None,
        config_path=None,
        host="127.0.0.1",
        port=9000,
        on_shutdown=ANY,
    )


def test_run_refuses_when_already_running(base_dir: Path):
    fd = acquire_lock("already-8080", base_dir=base_dir)
    try:
        with (
            patch(f"{_CLI_MODULE}._require_services_extra"),
            patch(f"{_CLI_MODULE}.compute_scope", return_value="already-8080"),
        ):
            result = runner.invoke(app, ["services", "run"])
        assert result.exit_code == 1
        assert "already running" in result.stderr
    finally:
        os.close(fd)


def test_run_writes_descriptor(base_dir: Path):
    mock_module = ModuleType("nmp.platform_runner.run")
    mock_module.run_platform = MagicMock()

    with (
        patch.dict("sys.modules", {"nmp.platform_runner.run": mock_module}),
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_PROCESS_MODULE}.get_create_time", return_value=1000.0),
    ):
        result = runner.invoke(
            app,
            ["services", "run", "--instance", "desc-test", "--port", "9999"],
        )

    assert result.exit_code == 0, result.stderr
    desc = read_descriptor("desc-test", base_dir=base_dir)
    assert desc is not None
    assert desc.mode == "foreground"
    assert desc.port == 9999


def test_run_records_background_mode_when_launched_by_start(base_dir: Path):
    mock_module = ModuleType("nmp.platform_runner.run")
    mock_module.run_platform = MagicMock()

    with (
        patch.dict("sys.modules", {"nmp.platform_runner.run": mock_module}),
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_PROCESS_MODULE}.get_create_time", return_value=1000.0),
        patch.dict(os.environ, {"_NMP_LAUNCH_MODE": "background"}),
    ):
        result = runner.invoke(
            app,
            ["services", "run", "--instance", "bg-mode-test", "--port", "9999"],
        )

    assert result.exit_code == 0, result.stderr
    desc = read_descriptor("bg-mode-test", base_dir=base_dir)
    assert desc is not None
    assert desc.mode == "background"


# ---------------------------------------------------------------------------
# start (background)
# ---------------------------------------------------------------------------


def test_start_shows_extra_hint_when_pyleak_missing():
    with patch(f"{_CLI_MODULE}.importlib.util.find_spec", side_effect=_no_pyleak):
        result = runner.invoke(app, ["services", "start"])
    assert result.exit_code == 1
    assert "nemo-platform[all]" in result.stderr


def test_start_launches_background(base_dir: Path):
    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_proc.poll.return_value = None

    with (
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_CLI_MODULE}.start_background", return_value=mock_proc),
        patch(f"{_CLI_MODULE}._wait_for_healthy", return_value=True),
    ):
        result = runner.invoke(
            app,
            ["services", "start", "--instance", "bg-test"],
        )

    assert result.exit_code == 0
    assert "99999" in result.stdout


def test_start_refuses_when_already_running(base_dir: Path):
    fd = acquire_lock("already-8080", base_dir=base_dir)
    try:
        with (
            patch(f"{_CLI_MODULE}._require_services_extra"),
            patch(f"{_CLI_MODULE}.compute_scope", return_value="already-8080"),
        ):
            result = runner.invoke(app, ["services", "start"])
        assert result.exit_code == 1
        assert "already running" in result.stderr
    finally:
        os.close(fd)


def test_start_exits_early_when_port_occupied_by_foreign_process(base_dir: Path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)

        with (
            patch(f"{_CLI_MODULE}._require_services_extra"),
            patch(f"{_CLI_MODULE}.start_background") as mock_start,
            patch(f"{_CLI_MODULE}.compute_scope", return_value=f"port-test-{port}"),
        ):
            result = runner.invoke(
                app,
                ["services", "start", "--port", str(port), "--instance", f"port-test-{port}"],
            )

    assert result.exit_code == 1
    assert "already in use" in result.stderr
    assert "lsof" in result.stderr
    assert "services.log" not in result.stderr
    mock_start.assert_not_called()


def test_run_exits_early_when_port_occupied_by_foreign_process(base_dir: Path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)

        with (
            patch(f"{_CLI_MODULE}._require_services_extra"),
            patch(f"{_CLI_MODULE}.compute_scope", return_value=f"run-port-test-{port}"),
        ):
            result = runner.invoke(
                app,
                ["services", "run", "--port", str(port), "--instance", f"run-port-test-{port}"],
            )

    assert result.exit_code == 1
    assert "already in use" in result.stderr
    assert "lsof" in result.stderr


def test_start_reports_failure(base_dir: Path):
    mock_proc = MagicMock()
    mock_proc.pid = 88888
    mock_proc.poll.return_value = 1

    with (
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_CLI_MODULE}.start_background", return_value=mock_proc),
        patch(f"{_CLI_MODULE}._wait_for_healthy", return_value=False),
    ):
        result = runner.invoke(
            app,
            ["services", "start", "--instance", "fail-test"],
        )

    assert result.exit_code == 1
    assert "exited early" in result.stderr


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


class TestServicesStop:
    def test_no_running_services(self, base_dir: Path):
        with patch(f"{_CLI_MODULE}.stop_instance", return_value=StopResult(stopped_pids=[])):
            result = runner.invoke(app, ["services", "stop", "--instance", "none"])
        assert result.exit_code == 0
        assert "not running" in result.stdout.lower()

    def test_stops_running_services(self, base_dir: Path):
        with patch(f"{_CLI_MODULE}.stop_instance", return_value=StopResult(stopped_pids=[12345])):
            result = runner.invoke(app, ["services", "stop", "--instance", "test"])
        assert result.exit_code == 0
        assert "12345" in result.stdout

    def test_stop_timeout_option(self, base_dir: Path):
        with patch(f"{_CLI_MODULE}.stop_instance", return_value=StopResult(stopped_pids=[])) as mock_stop:
            runner.invoke(app, ["services", "stop", "--timeout", "60", "--instance", "test"])
        _, kwargs = mock_stop.call_args
        assert kwargs["timeout"] == 60.0

    def test_stop_refuses_foreground_instance(self, base_dir: Path):
        with patch(
            f"{_CLI_MODULE}.stop_instance",
            side_effect=ForegroundInstanceError("fg-scope", 12345),
        ):
            result = runner.invoke(app, ["services", "stop", "--instance", "fg-scope"])
        assert result.exit_code == 1
        assert "foreground" in result.stderr

    def test_stop_force_overrides_foreground_protection(self, base_dir: Path):
        with patch(
            f"{_CLI_MODULE}.stop_instance",
            return_value=StopResult(stopped_pids=[12345]),
        ) as mock_stop:
            result = runner.invoke(
                app,
                ["services", "stop", "--instance", "fg-scope", "--force"],
            )
        assert result.exit_code == 0
        _, kwargs = mock_stop.call_args
        assert kwargs["force"] is True


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


class TestServicesRestart:
    def test_restart_rejects_services_with_service_group(self, base_dir: Path):
        result = runner.invoke(
            app,
            ["services", "restart", "--services", "entities", "--service-group", "default"],
        )
        assert result.exit_code != 0

    def test_restart_rejects_controllers_with_controller_group(self, base_dir: Path):
        result = runner.invoke(
            app,
            ["services", "restart", "--controllers", "jobs", "--controller-group", "default"],
        )
        assert result.exit_code != 0

    def test_restart_checks_extras_before_stopping(self, base_dir: Path):
        with (
            patch(f"{_CLI_MODULE}.importlib.util.find_spec", side_effect=_no_pyleak),
            patch(f"{_CLI_MODULE}.stop_instance") as mock_stop,
        ):
            result = runner.invoke(app, ["services", "restart"])
        assert result.exit_code == 1
        assert "nemo-platform[all]" in result.stderr
        mock_stop.assert_not_called()

    def test_restart_errors_when_no_prior_instance(self, base_dir: Path):
        with patch(f"{_CLI_MODULE}._require_services_extra"):
            result = runner.invoke(
                app,
                ["services", "restart", "--instance", "ghost"],
            )
        assert result.exit_code == 1
        assert "No instance found" in result.stderr
        assert "nemo services start" in result.stderr

    def test_restart_stops_and_starts(self, base_dir: Path):
        scope = "restart-test"
        fd = acquire_lock(scope, base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=os.getpid(),
            scope=scope,
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)

        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None

        try:
            with (
                patch(f"{_CLI_MODULE}._require_services_extra"),
                patch(f"{_CLI_MODULE}.stop_instance", return_value=StopResult(stopped_pids=[os.getpid()])),
                patch(f"{_CLI_MODULE}.start_background", return_value=mock_proc),
                patch(f"{_CLI_MODULE}._wait_for_healthy", return_value=True),
            ):
                result = runner.invoke(
                    app,
                    ["services", "restart", "--instance", scope],
                )
        finally:
            os.close(fd)

        assert result.exit_code == 0
        assert "restarted" in result.stdout.lower()

    def test_restart_exits_early_when_port_occupied_by_foreign_process(self, base_dir: Path):
        scope = "restart-foreign-port"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.listen(1)

            desc = InstanceDescriptor(
                pid=99999,
                scope=scope,
                host="127.0.0.1",
                port=port,
                mode="background",
                create_time=1.0,
            )
            write_descriptor(desc, base_dir=base_dir)

            with (
                patch(f"{_CLI_MODULE}._require_services_extra"),
                patch(f"{_CLI_MODULE}.stop_instance", return_value=StopResult(stopped_pids=[99999])),
                patch(f"{_CLI_MODULE}.start_background") as mock_start,
                patch(f"{_CLI_MODULE}.compute_scope", return_value=scope),
            ):
                result = runner.invoke(
                    app,
                    ["services", "restart", "--instance", scope, "--port", str(port)],
                )

        assert result.exit_code == 1
        assert "already in use" in result.stderr
        assert "lsof" in result.stderr
        assert "services.log" not in result.stderr
        mock_start.assert_not_called()

    def test_restart_preserves_previous_args(self, base_dir: Path):
        scope = "preserve-test"
        fd = acquire_lock(scope, base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=os.getpid(),
            scope=scope,
            host="127.0.0.1",
            port=9000,
            mode="background",
            create_time=1.0,
            services=["entities", "models"],
            controllers=["jobs"],
        )
        write_descriptor(desc, base_dir=base_dir)

        mock_proc = MagicMock()
        mock_proc.pid = 22222
        mock_proc.poll.return_value = None

        try:
            with (
                patch(f"{_CLI_MODULE}._require_services_extra"),
                patch(f"{_CLI_MODULE}.stop_instance", return_value=StopResult(stopped_pids=[os.getpid()])),
                patch(f"{_CLI_MODULE}.start_background", return_value=mock_proc) as mock_start,
                patch(f"{_CLI_MODULE}._wait_for_healthy", return_value=True),
            ):
                result = runner.invoke(
                    app,
                    ["services", "restart", "--instance", scope],
                )
        finally:
            os.close(fd)

        assert result.exit_code == 0
        _, kwargs = mock_start.call_args
        assert kwargs["services"] == ["entities", "models"]
        assert kwargs["controllers"] == ["jobs"]
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 9000


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestServicesStatus:
    def test_not_running(self, base_dir: Path):
        result = runner.invoke(app, ["services", "status", "--instance", "none"])
        assert result.exit_code == 0
        assert "No running instance" in result.stdout

    def test_running_instance(self, base_dir: Path):
        scope = "status-test"
        fd = acquire_lock(scope, base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=os.getpid(),
            scope=scope,
            host="127.0.0.1",
            port=8080,
            mode="foreground",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)

        try:
            with patch(f"{_CLI_MODULE}._wait_for_healthy", return_value=True):
                result = runner.invoke(app, ["services", "status", "--instance", scope])
        finally:
            os.close(fd)

        assert result.exit_code == 0
        assert scope in result.stdout
        assert str(os.getpid()) in result.stdout
        assert "foreground" in result.stdout
        assert "healthy" in result.stdout


# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


class TestServicesLs:
    def test_no_instances(self, base_dir: Path):
        result = runner.invoke(app, ["services", "ls"])
        assert result.exit_code == 0
        assert "No instances" in result.stdout

    def test_lists_running_instance(self, base_dir: Path):
        scope = "ls-test"
        fd = acquire_lock(scope, base_dir=base_dir)
        desc = InstanceDescriptor(
            pid=os.getpid(),
            scope=scope,
            host="127.0.0.1",
            port=8080,
            mode="background",
            create_time=1.0,
        )
        write_descriptor(desc, base_dir=base_dir)

        try:
            result = runner.invoke(app, ["services", "ls"])
        finally:
            os.close(fd)

        assert result.exit_code == 0
        assert scope in result.stdout
        assert "running" in result.stdout


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


class TestServicesLogs:
    def test_path_only(self, base_dir: Path):
        result = runner.invoke(
            app,
            ["services", "logs", "--path", "--instance", "log-test"],
        )
        assert result.exit_code == 0
        assert "services.log" in result.stdout

    def test_tail_log(self, base_dir: Path):
        scope = "tail-test"
        d = instance_dir(scope, base_dir=base_dir)
        (d / "services.log").write_text("line1\nline2\nline3\n")

        result = runner.invoke(
            app,
            ["services", "logs", "--instance", scope, "-n", "2"],
        )
        assert result.exit_code == 0
        assert "line2" in result.stdout
        assert "line3" in result.stdout

    def test_no_log_file(self, base_dir: Path):
        result = runner.invoke(
            app,
            ["services", "logs", "--instance", "nolog"],
        )
        assert result.exit_code == 0
        assert "No log file" in result.stdout


# ---------------------------------------------------------------------------
# Default host (127.0.0.1)
# ---------------------------------------------------------------------------


def test_default_host_is_loopback(base_dir: Path):
    mock_module = ModuleType("nmp.platform_runner.run")
    mock_run_platform = MagicMock()
    mock_module.run_platform = mock_run_platform

    with (
        patch.dict("sys.modules", {"nmp.platform_runner.run": mock_module}),
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_PROCESS_MODULE}.get_create_time", return_value=1000.0),
    ):
        result = runner.invoke(
            app,
            ["services", "run", "--instance", "loopback-test"],
        )

    assert result.exit_code == 0, result.stderr
    _, kwargs = mock_run_platform.call_args
    assert kwargs["host"] == "127.0.0.1"


def test_bind_all_warning(base_dir: Path):
    mock_module = ModuleType("nmp.platform_runner.run")
    mock_module.run_platform = MagicMock()

    with (
        patch.dict("sys.modules", {"nmp.platform_runner.run": mock_module}),
        patch(f"{_CLI_MODULE}._require_services_extra"),
        patch(f"{_PROCESS_MODULE}.get_create_time", return_value=1000.0),
    ):
        result = runner.invoke(
            app,
            ["services", "run", "--host", "0.0.0.0", "--instance", "warn-test"],
        )

    assert result.exit_code == 0
    assert "0.0.0.0" in result.stderr
    assert "network interfaces" in result.stderr


# ---------------------------------------------------------------------------
# start --services / --service-group mutual exclusion
# ---------------------------------------------------------------------------


def test_start_rejects_services_with_service_group(base_dir: Path):
    with patch(f"{_CLI_MODULE}._require_services_extra"):
        result = runner.invoke(
            app,
            ["services", "start", "--services", "a", "--service-group", "b"],
        )
    assert result.exit_code != 0


def test_start_rejects_controllers_with_controller_group(base_dir: Path):
    with patch(f"{_CLI_MODULE}._require_services_extra"):
        result = runner.invoke(
            app,
            ["services", "start", "--controllers", "a", "--controller-group", "b"],
        )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# _wait_for_healthy
# ---------------------------------------------------------------------------


class TestWaitForHealthy:
    """Unit tests for the health polling function."""

    def test_returns_true_on_immediate_200(self):
        from nemo_platform.cli.commands.services.cli import _wait_for_healthy

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch(f"{_CLI_MODULE}.httpx.get", return_value=mock_resp):
            result = _wait_for_healthy("127.0.0.1", 8080, timeout=5, poll_interval=0.1)

        assert result is True

    def test_returns_false_on_timeout(self):
        import httpx
        from nemo_platform.cli.commands.services.cli import _wait_for_healthy

        with patch(f"{_CLI_MODULE}.httpx.get", side_effect=httpx.ConnectError("")):
            result = _wait_for_healthy("127.0.0.1", 8080, timeout=0.3, poll_interval=0.1)

        assert result is False

    def test_retries_until_success(self):
        import httpx
        from nemo_platform.cli.commands.services.cli import _wait_for_healthy

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        call_count = 0

        def fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("")
            return mock_resp

        with patch(f"{_CLI_MODULE}.httpx.get", side_effect=fail_then_succeed):
            result = _wait_for_healthy("127.0.0.1", 8080, timeout=5, poll_interval=0.1)

        assert result is True
        assert call_count == 3

    def test_translates_wildcard_host_to_localhost(self):
        from nemo_platform.cli.commands.services.cli import _wait_for_healthy

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        captured_urls: list[str] = []

        def capture_get(url, **kwargs):
            captured_urls.append(url)
            return mock_resp

        with patch(f"{_CLI_MODULE}.httpx.get", side_effect=capture_get):
            _wait_for_healthy("0.0.0.0", 9090, timeout=2, poll_interval=0.1)

        assert "localhost" in captured_urls[0]
        assert "0.0.0.0" not in captured_urls[0]

    def test_non_200_keeps_polling(self):
        from nemo_platform.cli.commands.services.cli import _wait_for_healthy

        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_200 = MagicMock()
        resp_200.status_code = 200
        responses = [resp_503, resp_503, resp_200]

        with patch(f"{_CLI_MODULE}.httpx.get", side_effect=responses):
            result = _wait_for_healthy("127.0.0.1", 8080, timeout=5, poll_interval=0.1)

        assert result is True
