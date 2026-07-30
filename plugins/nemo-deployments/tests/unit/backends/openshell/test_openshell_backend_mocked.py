# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mocked-stub unit tests for OpenShellDeploymentBackend."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from nemo_deployments_plugin.backends.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
)
from nemo_deployments_plugin.backends.openshell.backend import (
    _LAUNCH_MARKER,
    _LIVENESS_PROBE,
    _MAX_ROUTABLE_NAME_LEN,
    _SERVE_DEAD_EXIT,
    _SERVE_PENDING_EXIT,
    _SERVE_PID_GRACE_SECONDS,
    _SERVE_PIDFILE,
    OpenShellDeploymentBackend,
    _sandbox_name,
    _service_name,
)
from nemo_deployments_plugin.backends.registry import BACKEND_CLASSES
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Container, ContainerPort, DeploymentConfig, EnvVar
from nemo_deployments_plugin.secrets import SecretResolutionError

pytest.importorskip("openshell")  # platform-restricted extra; skip where not installed (e.g. CI)

from openshell._proto import openshell_pb2 as pb  # ty: ignore[unresolved-import]


class FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode, details: str = "boom") -> None:
        self._code = code
        self._details = details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details


def _not_found() -> FakeRpcError:
    return FakeRpcError(grpc.StatusCode.NOT_FOUND, "missing")


def _sandbox(
    phase: int, *, sandbox_id: str = "sid", labels: dict | None = None, config_name: str = "cfg1"
) -> MagicMock:
    lbls = dict(labels or {})
    if config_name:
        lbls[CONFIG_NAME_LABEL] = config_name
    return MagicMock(
        sandbox=MagicMock(
            metadata=MagicMock(id=sandbox_id, labels=lbls),
            status=MagicMock(phase=phase, conditions=[]),
        )
    )


def _config(
    *,
    command: tuple[str, ...] = ("python3", "-m", "http.server"),
    args: tuple[str, ...] = ("8000",),
    with_port: bool = True,
) -> DeploymentConfig:
    ports = [ContainerPort(containerPort=8000, name="http")] if with_port else []
    return DeploymentConfig(
        name="cfg1",
        workspace="default",
        containers=[Container(name="web", image="img:latest", command=list(command), args=list(args), ports=ports)],
    )


def _exec_events(exit_code: int, *, stdout: str = "", stderr: str = "") -> list[MagicMock]:
    """Build a realistic ExecSandbox event stream: optional stdout/stderr then an exit event."""
    events: list[MagicMock] = []
    if stdout:
        out = MagicMock()
        out.HasField.side_effect = lambda field: field == "stdout"
        out.stdout.data = stdout.encode()
        events.append(out)
    if stderr:
        err = MagicMock()
        err.HasField.side_effect = lambda field: field == "stderr"
        err.stderr.data = stderr.encode()
        events.append(err)
    exit_event = MagicMock()
    exit_event.HasField.side_effect = lambda field: field == "exit"
    exit_event.exit.exit_code = exit_code
    events.append(exit_event)
    return events


def _config_with_env(env: list[EnvVar]) -> DeploymentConfig:
    return DeploymentConfig(
        name="cfg1",
        workspace="default",
        containers=[
            Container(
                name="web",
                image="img:latest",
                command=["python3", "-m", "http.server"],
                args=["8000"],
                ports=[ContainerPort(containerPort=8000, name="http")],
                env=env,
            )
        ],
    )


def test_registry_contains_openshell() -> None:
    assert BACKEND_CLASSES["openshell"] is OpenShellDeploymentBackend


def test_sandbox_name_within_limit_and_deterministic() -> None:
    name = _sandbox_name("a-long-workspace-name", "a-long-deployment-name")
    assert name.startswith("nmp-")
    assert len(name) <= _MAX_ROUTABLE_NAME_LEN
    assert name == _sandbox_name("a-long-workspace-name", "a-long-deployment-name")
    assert name != _sandbox_name("other", "name")


def test_service_name_clamped_and_distinct() -> None:
    short = _service_name(ContainerPort(containerPort=8000, name="http"))
    assert short == "http"

    unnamed = _service_name(ContainerPort(containerPort=8000))
    assert unnamed == "port-8000"

    long_a = _service_name(ContainerPort(containerPort=8000, name="a-very-long-port-name-one"))
    long_b = _service_name(ContainerPort(containerPort=8001, name="a-very-long-port-name-two"))
    assert len(long_a) <= _MAX_ROUTABLE_NAME_LEN
    assert not long_a.endswith("-")
    assert long_a != long_b, "truncation must not collapse distinct port names onto one service"


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        # READY is not here: a READY sandbox triggers the read_status provisioning state
        # machine (launch/expose), covered by the read_status provisioning tests below.
        (pb.SANDBOX_PHASE_PROVISIONING, "STARTING"),
        (pb.SANDBOX_PHASE_ERROR, "FAILED"),
        (pb.SANDBOX_PHASE_DELETING, "DELETING"),
    ],
)
async def test_read_status_maps_phase(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, phase: int, expected: str
) -> None:
    mock_stub.GetSandbox.return_value = _sandbox(phase)
    update = await openshell_backend.read_status(workspace="default", name="srv")
    assert update.status == expected


async def test_read_status_includes_exposed_endpoints(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    svc = MagicMock(url="http://nmp-x--http.openshell.localhost:18080/")
    svc.endpoint.service_name = "http"
    mock_stub.ListServices.return_value = MagicMock(services=[svc])

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"
    assert [e.url for e in update.endpoints] == ["http://nmp-x--http.openshell.localhost:18080/"]
    assert update.endpoints[0].name == "http"


async def test_read_status_not_found_is_lost(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    mock_stub.GetSandbox.side_effect = _not_found()
    update = await openshell_backend.read_status(workspace="default", name="srv")
    assert update.status == "LOST"


async def test_create_requires_serve_command(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_stub.GetSandbox.side_effect = _not_found()  # not already present
    mock_entities.get.return_value = _config(command=(), args=())
    update = await openshell_backend.create_deployment(
        workspace="default", name="srv", config_name="cfg1", labels={}, backend_config={}
    )
    assert update.status == "FAILED"
    assert "command" in update.status_message


async def test_create_returns_starting_after_create(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # Create returns STARTING right after CreateSandbox; provisioning (launch/expose) is
    # deferred to read_status so a slow sandbox never blocks the reconcile loop.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.side_effect = _not_found()  # idempotency probe: absent
    mock_stub.CreateSandbox.return_value = MagicMock()

    update = await openshell_backend.create_deployment(
        workspace="default", name="srv", config_name="cfg1", labels={"managed-by": MANAGED_BY_LABEL}, backend_config={}
    )

    assert update.status == "STARTING"
    mock_stub.CreateSandbox.assert_called_once()
    mock_stub.ExecSandbox.assert_not_called()
    mock_stub.ExposeService.assert_not_called()


async def test_delete_idempotent_when_missing(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    mock_stub.DeleteSandbox.side_effect = _not_found()
    update = await openshell_backend.delete_deployment("default", "srv")
    assert update.status == "SUCCEEDED"


async def test_list_managed_deployment_names(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    sandbox = MagicMock(
        metadata=MagicMock(
            labels={
                MANAGED_BY_KEY: MANAGED_BY_LABEL,
                DEPLOYMENT_WORKSPACE_LABEL: "default",
                DEPLOYMENT_NAME_LABEL: "srv",
            }
        )
    )
    mock_stub.ListSandboxes.return_value = MagicMock(sandboxes=[sandbox])
    names = await openshell_backend.list_managed_deployment_names()
    assert names == ["default/srv"]


async def test_get_logs_formats_lines(openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock) -> None:
    # No workload log yet (the tail exec reports no exit code) -> supervisor logs.
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY, sandbox_id="sid")
    log_line = MagicMock(source="sandbox")
    log_line.message = "serving on 8000"
    mock_stub.GetSandboxLogs.return_value = MagicMock(logs=[log_line], buffer_total=1)

    result = await openshell_backend.get_logs(workspace="default", name="srv", tail=10)
    assert result.lines == ["[sandbox] serving on 8000"]


async def test_get_logs_returns_workload_log(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY, sandbox_id="sid")
    mock_stub.ExecSandbox.return_value = _exec_events(0, stdout="starting nat\nlistening on 8000\n")

    result = await openshell_backend.get_logs(workspace="default", name="srv", tail=10)

    assert result.lines == ["starting nat", "listening on 8000"]
    mock_stub.GetSandboxLogs.assert_not_called()


async def test_create_volume_unsupported(openshell_backend: OpenShellDeploymentBackend) -> None:
    update = await openshell_backend.create_volume(
        workspace="default", name="data", size="1Gi", access_modes=["ReadWriteOnce"], backend_config={}
    )
    assert update.status == "FAILED"


# --- #2: secrets resolved; unresolved env fails FAILED, no silent drop ---


async def test_create_resolves_plain_env_into_sandbox(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.return_value = _config_with_env([EnvVar(name="FOO", value="bar")])
    mock_stub.GetSandbox.side_effect = _not_found()  # idempotency probe: absent
    mock_stub.CreateSandbox.return_value = MagicMock()

    update = await openshell_backend.create_deployment(
        workspace="default", name="srv", config_name="cfg1", labels={}, backend_config={}
    )

    assert update.status == "STARTING"
    spec = mock_stub.CreateSandbox.call_args.args[0].spec
    assert spec.environment["FOO"] == "bar"


async def test_create_fails_on_unresolved_value_from(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_stub.GetSandbox.side_effect = _not_found()  # not already present
    mock_entities.get.return_value = _config_with_env(
        [EnvVar(name="POD_IP", valueFrom={"fieldRef": {"fieldPath": "status.podIP"}})]
    )

    update = await openshell_backend.create_deployment(
        workspace="default", name="srv", config_name="cfg1", labels={}, backend_config={}
    )

    assert update.status == "FAILED"
    assert "POD_IP" in update.status_message
    mock_stub.CreateSandbox.assert_not_called()


async def test_create_fails_when_secret_resolution_errors(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_stub.GetSandbox.side_effect = _not_found()
    mock_entities.get.return_value = _config()
    with patch(
        "nemo_deployments_plugin.backends.openshell.backend.resolve_deployment_config_secrets",
        side_effect=SecretResolutionError("Platform secret access failed"),
    ):
        update = await openshell_backend.create_deployment(
            workspace="default", name="srv", config_name="cfg1", labels={}, backend_config={}
        )

    assert update.status == "FAILED"
    assert "secret" in update.status_message.lower()
    mock_stub.CreateSandbox.assert_not_called()


# --- #6/#7/#8: read_status drives provisioning; failures clean up the sandbox ---


async def test_read_status_launches_serve_when_ready(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # READY, no services yet, marker absent -> launch serve, report STARTING.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = [_exec_events(1), _exec_events(0)]  # marker absent, launch ok

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "STARTING"
    mock_stub.ExposeService.assert_not_called()


async def test_read_status_transient_rpc_error_is_unknown(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # A transient RPC error on the serve-marker probe must not escape read_status; it maps to
    # UNKNOWN (retry next poll) rather than deleting the sandbox or relaunching.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = FakeRpcError(grpc.StatusCode.UNAVAILABLE, "gateway blip")

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "UNKNOWN"
    mock_stub.DeleteSandbox.assert_not_called()


async def test_read_status_exposes_after_launch(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # READY, no services, marker present -> expose ports -> READY with endpoint.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.return_value = _exec_events(0)  # marker present
    mock_stub.ExposeService.return_value = MagicMock(url="http://nmp-x--http.openshell.localhost:17670/")

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"
    assert [e.url for e in update.endpoints] == ["http://nmp-x--http.openshell.localhost:17670/"]


async def test_read_status_fails_when_serve_process_died(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    # Ports exposed but the workload is gone.
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    svc = MagicMock(url="http://nmp-x--http.openshell.localhost:17670/")
    svc.endpoint.service_name = "http"
    mock_stub.ListServices.return_value = MagicMock(services=[svc])
    mock_stub.ExecSandbox.side_effect = [
        _exec_events(9),  # liveness probe: pid is gone
        _exec_events(0, stdout="ValueError: unknown model\n"),  # log tail
    ]

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    assert "unknown model" in update.status_message
    mock_stub.DeleteSandbox.assert_not_called()  # kept so get_logs can still read the log


async def test_read_status_does_not_expose_a_dead_workload(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # Launched on an earlier poll, process already dead.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = [
        _exec_events(0),  # marker present
        _exec_events(9),  # liveness probe: pid is gone
        _exec_events(0, stdout="Traceback: boom\n"),  # log tail
    ]

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    assert "boom" in update.status_message
    mock_stub.ExposeService.assert_not_called()


async def test_read_status_stays_ready_when_liveness_is_undecidable(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock
) -> None:
    # Already serving and the probe cannot decide: only proof of death demotes a
    # deployment, so an undecided probe must not flap it.
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    svc = MagicMock(url="http://nmp-x--http.openshell.localhost:17670/")
    svc.endpoint.service_name = "http"
    mock_stub.ListServices.return_value = MagicMock(services=[svc])
    mock_stub.ExecSandbox.return_value = _exec_events(10)

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"


async def test_read_status_withholds_expose_until_the_serve_pid_exists(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # The launcher marks the launch unconditionally, so a marker alone proves nothing.
    # Until a pid is recorded the deployment stays STARTING rather than advancing to
    # expose and reporting READY over a workload that may never have started.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = [
        _exec_events(0),  # marker present
        _exec_events(10),  # liveness probe: no pidfile yet, still inside the grace window
    ]

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "STARTING"
    mock_stub.ExposeService.assert_not_called()


async def test_read_status_fails_when_the_serve_pid_never_appears(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # Past the grace window a missing pidfile is proof the launcher's background shell
    # never ran, which is a failed deployment rather than a slow one.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = [
        _exec_events(0),  # marker present
        _exec_events(9),  # liveness probe: grace elapsed with no pidfile
        _exec_events(0, stdout="sh: 1: nat: not found\n"),  # log tail
    ]

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    assert "not found" in update.status_message
    mock_stub.ExposeService.assert_not_called()


async def test_read_status_deletes_sandbox_when_launch_rpc_fails(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = [_exec_events(1), FakeRpcError(grpc.StatusCode.INTERNAL, "exec boom")]

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    mock_stub.DeleteSandbox.assert_called_once()


async def test_read_status_fails_on_nonzero_launch_exit(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.side_effect = [_exec_events(1), _exec_events(127, stderr="sh: setsid: not found")]

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    assert "127" in update.status_message
    assert "setsid" in update.status_message
    mock_stub.ExposeService.assert_not_called()
    mock_stub.DeleteSandbox.assert_called_once()


async def test_read_status_deletes_sandbox_when_expose_fails(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.return_value = _exec_events(0)  # marker present -> expose path
    mock_stub.ExposeService.side_effect = FakeRpcError(grpc.StatusCode.INTERNAL, "expose boom")

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    mock_stub.DeleteSandbox.assert_called_once()


async def test_read_status_cleanup_swallows_delete_error(
    openshell_backend: OpenShellDeploymentBackend, mock_stub: MagicMock, mock_entities: AsyncMock
) -> None:
    # Cleanup must not mask the original provisioning failure even if DeleteSandbox errors.
    mock_entities.get.return_value = _config()
    mock_stub.GetSandbox.return_value = _sandbox(pb.SANDBOX_PHASE_READY)
    mock_stub.ExecSandbox.return_value = _exec_events(0)
    mock_stub.ExposeService.side_effect = FakeRpcError(grpc.StatusCode.INTERNAL, "expose boom")
    mock_stub.DeleteSandbox.side_effect = FakeRpcError(grpc.StatusCode.INTERNAL, "delete boom")

    update = await openshell_backend.read_status(workspace="default", name="srv")

    assert update.status == "FAILED"
    assert "expose" in update.status_message.lower()
    mock_stub.DeleteSandbox.assert_called_once()


def _run_probe(tmp_path: Path, *, pid: str | None, marker: str | None) -> int:
    """Run the real liveness probe against tmp files, returning its exit code.

    The probe is shell, not Python, so the three-state logic is only meaningful when
    executed by a shell. Paths are rewritten to tmp_path so the test never touches the
    constants' real locations.
    """
    pidfile = tmp_path / "serve.pid"
    marker_file = tmp_path / "serve.launched"
    if pid is not None:
        pidfile.write_text(pid)
    if marker is not None:
        marker_file.write_text(marker)
    script = _LIVENESS_PROBE.replace(_SERVE_PIDFILE, str(pidfile)).replace(_LAUNCH_MARKER, str(marker_file))
    return subprocess.run(["/bin/sh", "-c", script], capture_output=True, check=False).returncode


def test_liveness_probe_reports_a_live_pid_as_alive(tmp_path: Path) -> None:
    # The test process itself: alive, and owned by this user so kill -0 is permitted
    # (an unowned pid fails with EPERM and would read as dead).
    assert _run_probe(tmp_path, pid=str(os.getpid()), marker=str(int(time.time()))) == 0


def test_liveness_probe_reports_a_reaped_pid_as_dead(tmp_path: Path) -> None:
    dead = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
    dead.wait()
    assert _run_probe(tmp_path, pid=str(dead.pid), marker=str(int(time.time()))) == _SERVE_DEAD_EXIT


def test_liveness_probe_is_pending_while_the_pidfile_is_still_expected(tmp_path: Path) -> None:
    # Launched a moment ago with no pid recorded yet: a slow start, not a failure.
    assert _run_probe(tmp_path, pid=None, marker=str(int(time.time()))) == _SERVE_PENDING_EXIT


def test_liveness_probe_ages_a_missing_pidfile_into_dead(tmp_path: Path) -> None:
    # This is the hole the three-state probe closes: the launcher marks the launch
    # unconditionally, so without the grace check a pidfile that never appears reads as
    # healthy forever and the deployment advances to READY over nothing.
    stale = int(time.time()) - _SERVE_PID_GRACE_SECONDS - 1
    assert _run_probe(tmp_path, pid=None, marker=str(stale)) == _SERVE_DEAD_EXIT


@pytest.mark.parametrize("marker", [None, "", "not-a-timestamp"])
def test_liveness_probe_is_pending_when_the_marker_is_unusable(tmp_path: Path, marker: str | None) -> None:
    # No usable launch time means no basis to call it dead, so stay undecided rather
    # than fail a deployment on a garbled marker.
    assert _run_probe(tmp_path, pid=None, marker=marker) == _SERVE_PENDING_EXIT
