# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenShell substrate backend for the deployments plugin.

Runs a deployment as an OpenShell sandbox: create the sandbox from the container
image, launch the serve command as a detached process (the supervisor is PID 1, so
the workload is started via ``ExecSandbox`` rather than the image entrypoint), and
publish each container port with ``ExposeService`` to obtain a gateway-routable URL.

The proto stubs and gRPC client come from the ``openshell`` SDK (``openshell._proto``).
Each sandbox gets a ``SandboxPolicy``: either a hand-written YAML (``default_policy_path``)
or a generated default-deny policy built from the platform egress + the sandbox
filesystem defaults, with the platform egress rule always injected as mandatory so
the agent's own fs paths and its path back to the platform are permitted. Not yet
covered and tracked separately:
- persistent volumes;
- supervisor-managed (restartable) workload command; the detached exec is not
  supervised, so the reconciler probes its liveness and reports FAILED when it
  dies, rather than restarting it.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shlex
from typing import TYPE_CHECKING, Any, Literal, cast

from nemo_deployments_plugin.backends.base import (
    BackendStatusUpdate,
    DeploymentBackend,
    LogResult,
    MissingBackendDependencyError,
    VolumeStatusUpdate,
)
from nemo_deployments_plugin.backends.labels import (
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    deployment_identity_labels,
    managed_by_label_selector,
)
from nemo_deployments_plugin.backends.openshell.config import OpenShellExecutorConfig
from nemo_deployments_plugin.backends.openshell.policy import (
    DEFAULT_EGRESS_BINARIES,
    PlatformEgress,
    SandboxFilesystem,
    build_sandbox_policy,
    generate_policy_dict,
    inject_platform_egress,
    load_policy_dict,
    normalize_loaded_policy,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Container, DeploymentConfig
from nemo_deployments_plugin.secrets import SecretResolutionError, resolve_deployment_config_secrets
from nemo_deployments_plugin.types import DeploymentStatus, Endpoint
from nemo_platform.resources.entities import AsyncEntitiesResource
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError

if TYPE_CHECKING:
    import grpc
    from openshell._proto import openshell_pb2 as pb  # ty: ignore[unresolved-import]
    from openshell._proto import openshell_pb2_grpc as pb_grpc  # ty: ignore[unresolved-import]

logger = logging.getLogger(__name__)

_OPENSHELL_INSTALL_HINT = (
    "The 'openshell' package is required for OpenShellDeploymentBackend. "
    "Install it with: uv sync --package nemo-deployments-plugin --extra openshell"
)

_SERVE_LOG = "/tmp/nemo-serve.log"
# Marker the serve launcher writes so read_status (stateless across reconcile polls)
# does not relaunch the workload on a later poll. Lives in a policy read-write path.
# Holds the launch time as epoch seconds, which is the only clock the probe has for
# deciding whether a missing pidfile is a slow start or a launcher that never ran.
_LAUNCH_MARKER = "/tmp/nemo-serve.launched"
_SERVE_PIDFILE = "/tmp/nemo-serve.pid"

# OpenShell rejects a longer sandbox or service name with INVALID_ARGUMENT: three
# segments plus two "--" delimiters must fit a 63-char DNS label.
_MAX_ROUTABLE_NAME_LEN = 19

# Seconds after launch that a missing pidfile stops being a slow start and becomes proof
# the launcher's background shell never ran.
_SERVE_PID_GRACE_SECONDS = 30

# Liveness probe exit codes. The launcher backgrounds the workload and marks the launch
# unconditionally, so the marker only proves the shell accepted the `&`. The pidfile is
# what proves something actually started, hence the third state: absent-but-recent is
# pending (wait another poll), absent-past-grace is dead.
_SERVE_DEAD_EXIT = 9
_SERVE_PENDING_EXIT = 10
_LIVENESS_PROBE = f"""
if test -f {_SERVE_PIDFILE}; then
  kill -0 "$(cat {_SERVE_PIDFILE})" 2>/dev/null || exit {_SERVE_DEAD_EXIT}
  exit 0
fi
started=$(cat {_LAUNCH_MARKER} 2>/dev/null) || exit {_SERVE_PENDING_EXIT}
case "$started" in '' | *[!0-9]*) exit {_SERVE_PENDING_EXIT} ;; esac
if [ "$(($(date +%s) - started))" -ge {_SERVE_PID_GRACE_SECONDS} ]; then
  exit {_SERVE_DEAD_EXIT}
fi
exit {_SERVE_PENDING_EXIT}
"""
_LOG_TAIL_LINES = 20

# Cached on first status read; needs the proto enums so it cannot be built at import
# time (see _ensure_openshell). None until built.
_PHASE_TO_STATUS: dict[int, DeploymentStatus] | None = None


def _ensure_openshell() -> None:
    """Import grpc + the openshell proto stubs, binding them as module globals.

    Deferred so importing this backend (and the registry that eagerly imports it)
    does not require the optional ``openshell`` package, matching the docker/k8s
    backends. Only ``TYPE_CHECKING`` imports the names, so the type checker sees pure
    modules (never ``None``); the runtime binding lives in ``globals()``. Constructing
    the backend calls this and raises a clear error when the package is absent.
    """
    if globals().get("pb") is not None:
        return
    try:
        import grpc
        from openshell._proto import openshell_pb2 as pb  # ty: ignore[unresolved-import]
        from openshell._proto import openshell_pb2_grpc as pb_grpc  # ty: ignore[unresolved-import]
    except ImportError as exc:
        raise MissingBackendDependencyError(_OPENSHELL_INSTALL_HINT) from exc
    globals().update(grpc=grpc, pb=pb, pb_grpc=pb_grpc)


def _phase_to_status(phase: int) -> DeploymentStatus:
    global _PHASE_TO_STATUS
    if _PHASE_TO_STATUS is None:
        _PHASE_TO_STATUS = {
            pb.SANDBOX_PHASE_UNSPECIFIED: "UNKNOWN",
            pb.SANDBOX_PHASE_PROVISIONING: "STARTING",
            pb.SANDBOX_PHASE_READY: "READY",
            pb.SANDBOX_PHASE_ERROR: "FAILED",
            pb.SANDBOX_PHASE_DELETING: "DELETING",
            pb.SANDBOX_PHASE_UNKNOWN: "UNKNOWN",
        }
    return _PHASE_TO_STATUS.get(phase, "UNKNOWN")


class OpenShellDeploymentBackend(DeploymentBackend):
    """Manage deployments as OpenShell sandboxes via the gateway gRPC API."""

    def init(self) -> None:
        _ensure_openshell()
        self._executor_config = OpenShellExecutorConfig.model_validate(self._config)
        self._entities = NemoEntitiesClient(AsyncEntitiesResource(self._sdk))
        # Build the policy once (fail fast on a bad path/shape). The gateway default
        # policy would not permit the agent's own exec paths, so we always apply one.
        self._policy = self._build_executor_policy()
        self._channel = self._create_channel()
        self._stub = pb_grpc.OpenShellStub(self._channel)

    def _build_executor_policy(self) -> Any:
        """The SandboxPolicy applied to created sandboxes.

        A hand-written YAML (``default_policy_path``) if given, else a generated
        default-deny policy. When ``platform_egress`` is configured, its rule is
        injected as mandatory so the sandbox can always reach the platform.
        When ``platform_egress`` is null the sandbox gets no direct
        egress at all, correct for gateway-managed inference (inference.local),
        which the supervisor brokers so no policy egress rule is needed. The
        supervisor still dials the platform itself, at the sandbox network's
        gateway address, so the platform must listen there (``--host 0.0.0.0``).
        """
        cfg = self._executor_config.platform_egress
        egress = (
            PlatformEgress(
                host=cfg.host,
                port=cfg.port,
                protocol=cfg.protocol,
                tls=cfg.tls,
                access=cfg.access,
                binaries=tuple(cfg.binaries) or DEFAULT_EGRESS_BINARIES,
            )
            if cfg is not None
            else None
        )
        compat = self._executor_config.landlock_compatibility
        path = self._executor_config.default_policy_path
        if path:
            policy_dict = normalize_loaded_policy(load_policy_dict(path), landlock_compatibility=compat)
        else:
            policy_dict = generate_policy_dict(
                filesystem=SandboxFilesystem(landlock_compatibility=compat), egress=egress
            )
        if egress is not None:
            inject_platform_egress(policy_dict, egress)
        return build_sandbox_policy(policy_dict)

    def _create_channel(self) -> grpc.Channel:
        target = self._executor_config.grpc_target()
        if self._executor_config.use_insecure():
            return grpc.insecure_channel(target)
        tls = self._executor_config.tls
        ca = client_cert = client_key = None
        if tls is not None:
            ca = _read_bytes(tls.ca_cert_path)
            client_cert = _read_bytes(tls.client_cert_path)
            client_key = _read_bytes(tls.client_key_path)
        credentials = grpc.ssl_channel_credentials(
            root_certificates=ca,
            private_key=client_key,
            certificate_chain=client_cert,
        )
        return grpc.secure_channel(target, credentials)

    def shutdown(self) -> None:
        channel = getattr(self, "_channel", None)
        if channel is not None:
            channel.close()

    async def _load_deployment_config(self, workspace: str, config_name: str) -> DeploymentConfig:
        return await self._entities.get(DeploymentConfig, config_name, workspace=workspace)

    async def create_deployment(
        self,
        *,
        workspace: str,
        name: str,
        config_name: str,
        labels: dict[str, str],
        backend_config: dict[str, Any],
    ) -> BackendStatusUpdate:
        del backend_config  # per-deployment openshell overrides: needs entity field + SDK regen (follow-up)
        sandbox_nm = _sandbox_name(workspace, name)

        existing = await self._try_get_sandbox(sandbox_nm)
        if existing is not None:
            if _sandbox_matches(existing, workspace, name):
                return await self.read_status(workspace=workspace, name=name)
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Sandbox name collision: {sandbox_nm} exists with different labels",
            )

        try:
            config = await self._load_deployment_config(workspace, config_name)
            config = await resolve_deployment_config_secrets(self._sdk, config)
        except NemoEntityNotFoundError:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"DeploymentConfig '{config_name}' not found in workspace '{workspace}'",
            )
        except SecretResolutionError as exc:
            return BackendStatusUpdate(status="FAILED", status_message=str(exc))
        except Exception as exc:
            logger.exception("Failed to load deployment config %s/%s", workspace, config_name)
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"Failed to load deployment config: {exc}",
            )

        if not config.containers:
            return BackendStatusUpdate(status="FAILED", status_message="DeploymentConfig has no containers")
        container = config.containers[0]
        if not container.image:
            return BackendStatusUpdate(status="FAILED", status_message="containers[0].image is required")

        serve_command = list(container.command) + list(container.args)
        if not serve_command:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=(
                    "openshell backend requires containers[0].command (the serve command); "
                    "the image entrypoint is not run by the sandbox supervisor"
                ),
            )

        env: dict[str, str] = {}
        unresolved: list[str] = []
        for var in container.env:
            if var.value is not None:
                env[var.name] = var.value
            elif var.value_from is not None or var.secret_ref is not None:
                unresolved.append(var.name)
        if unresolved:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=(
                    "Cannot resolve a value for environment variable(s): "
                    f"{', '.join(sorted(unresolved))}. valueFrom is not supported by the openshell "
                    "backend and secret references must resolve to a value."
                ),
            )
        all_labels = {
            **labels,
            **config.labels,
            **deployment_identity_labels(
                workspace,
                name,
                config.restart_policy,
                config_name=config_name,
                backoff_limit=config.backoff_limit,
            ),
        }

        template = pb.SandboxTemplate(image=container.image, environment=env, labels=all_labels)
        spec = pb.SandboxSpec(template=template, environment=env, policy=self._policy)
        request = pb.CreateSandboxRequest(spec=spec, name=sandbox_nm, labels=all_labels)

        try:
            await self._unary(self._stub.CreateSandbox, request)
        except grpc.RpcError as exc:
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"CreateSandbox failed: {_rpc_detail(exc)}",
            )

        # Return as soon as the sandbox is created. Provisioning (wait for READY, launch
        # the serve command, expose ports) is driven by read_status across the reconciler's
        # poll cycles, so a slow sandbox never blocks the serial reconcile loop.
        return BackendStatusUpdate(
            status="STARTING",
            status_message=f"Sandbox {sandbox_nm} created; awaiting READY",
        )

    async def read_status(self, *, workspace: str, name: str) -> BackendStatusUpdate:
        sandbox_nm = _sandbox_name(workspace, name)
        try:
            response = await self._unary(self._stub.GetSandbox, pb.GetSandboxRequest(name=sandbox_nm))
        except grpc.RpcError as exc:
            if _rpc_code(exc) == grpc.StatusCode.NOT_FOUND:
                return BackendStatusUpdate(status="LOST", status_message=f"Sandbox {sandbox_nm} not found")
            return BackendStatusUpdate(
                status="UNKNOWN",
                status_message=f"GetSandbox error: {_rpc_detail(exc)}",
                error_details={"error": _rpc_detail(exc), "sandbox": sandbox_nm},
            )

        sandbox = response.sandbox
        phase = sandbox.status.phase
        # Not READY yet: report the phase and let the reconciler keep polling.
        if phase != pb.SANDBOX_PHASE_READY:
            status = _phase_to_status(phase)
            message = _condition_message(sandbox.status) or f"Sandbox phase {pb.SandboxPhase.Name(phase)}"
            return BackendStatusUpdate(status=status, status_message=message)

        # Sandbox READY: drive provisioning (launch the serve command, expose ports) on
        # the reconciler's poll cycles rather than blocking create.
        try:
            return await self._advance_provisioning(sandbox, sandbox_nm, workspace)
        except grpc.RpcError as exc:
            # A transient gateway error mid-provisioning (e.g. the serve-marker probe) must not
            # escape raw into the reconciler; report UNKNOWN and let the next poll retry. The
            # deliberate provisioning-failure paths already return FAILED and clean up, so this
            # only catches unhandled transients.
            return BackendStatusUpdate(
                status="UNKNOWN",
                status_message=f"Provisioning RPC error: {_rpc_detail(exc)}",
                error_details={"error": _rpc_detail(exc), "sandbox": sandbox_nm},
            )

    async def delete_deployment(self, workspace: str, name: str) -> BackendStatusUpdate:
        sandbox_nm = _sandbox_name(workspace, name)
        try:
            await self._unary(self._stub.DeleteSandbox, pb.DeleteSandboxRequest(name=sandbox_nm))
        except grpc.RpcError as exc:
            if _rpc_code(exc) == grpc.StatusCode.NOT_FOUND:
                return BackendStatusUpdate(
                    status="SUCCEEDED",
                    status_message=f"Sandbox {sandbox_nm} already gone",
                )
            return BackendStatusUpdate(
                status="FAILED",
                status_message=f"DeleteSandbox failed: {_rpc_detail(exc)}",
            )
        return BackendStatusUpdate(status="SUCCEEDED", status_message=f"Sandbox {sandbox_nm} deleted")

    async def list_managed_deployment_names(self) -> list[str]:
        request = pb.ListSandboxesRequest(label_selector=managed_by_label_selector())
        try:
            response = await self._unary(self._stub.ListSandboxes, request)
        except grpc.RpcError:
            logger.warning("Failed to list managed sandboxes", exc_info=True)
            return []

        seen: set[str] = set()
        for sandbox in response.sandboxes:
            sandbox_labels = dict(sandbox.metadata.labels)
            if sandbox_labels.get(MANAGED_BY_KEY) != MANAGED_BY_LABEL:
                continue
            ws = sandbox_labels.get(DEPLOYMENT_WORKSPACE_LABEL)
            dep_name = sandbox_labels.get(DEPLOYMENT_NAME_LABEL)
            if ws and dep_name:
                seen.add(f"{ws}/{dep_name}")
        return sorted(seen)

    async def get_logs(self, *, workspace: str, name: str, tail: int = 100) -> LogResult:
        """Tail the workload's own output, falling back to the supervisor log.

        ``GetSandboxLogs`` cannot see ``_SERVE_LOG``: it is fed by the supervisor's
        tracing layer, not by the workload's stdout.
        """
        sandbox_nm = _sandbox_name(workspace, name)
        try:
            sandbox = await self._unary(self._stub.GetSandbox, pb.GetSandboxRequest(name=sandbox_nm))
            sandbox_id = sandbox.sandbox.metadata.id or sandbox_nm
            exit_code, output = await self._exec_detached(
                sandbox_id, ["/bin/sh", "-lc", f"tail -n {int(tail)} {_SERVE_LOG}"]
            )
            if exit_code == 0:
                lines = output.splitlines()
                return LogResult(lines=lines, truncated=len(lines) >= tail)
            response = await self._unary(
                self._stub.GetSandboxLogs,
                pb.GetSandboxLogsRequest(sandbox_id=sandbox_id, lines=tail),
            )
        except grpc.RpcError as exc:
            if _rpc_code(exc) == grpc.StatusCode.NOT_FOUND:
                return LogResult(lines=[f"Sandbox {sandbox_nm} not found"])
            return LogResult(lines=[f"Failed to fetch logs: {_rpc_detail(exc)}"])
        lines = [_format_log_line(line) for line in response.logs]
        return LogResult(lines=lines, truncated=response.buffer_total > len(lines))

    async def create_volume(
        self,
        *,
        workspace: str,
        name: str,
        size: str,
        access_modes: list[str],
        backend_config: dict[str, Any],
    ) -> VolumeStatusUpdate:
        del workspace, name, size, access_modes, backend_config
        return VolumeStatusUpdate(
            status="FAILED",
            status_message="Volumes are not yet supported by the openshell backend",
        )

    async def read_volume_status(
        self,
        *,
        workspace: str,
        name: str,
        backend_config: dict[str, Any] | None = None,
    ) -> VolumeStatusUpdate:
        del workspace, name, backend_config
        return VolumeStatusUpdate(
            status="FAILED",
            status_message="Volumes are not yet supported by the openshell backend",
        )

    async def delete_volume(
        self,
        workspace: str,
        name: str,
        *,
        backend_config: dict[str, Any] | None = None,
    ) -> VolumeStatusUpdate:
        del workspace, name, backend_config
        return VolumeStatusUpdate(status="RELEASED", status_message="No openshell volume to delete")

    # --- helpers ---

    async def _unary(self, method: Any, request: Any) -> Any:
        return await asyncio.to_thread(method, request, timeout=self._executor_config.request_timeout_seconds)

    async def _advance_provisioning(self, sandbox: Any, sandbox_nm: str, workspace: str) -> BackendStatusUpdate:
        """Advance a READY sandbox toward a serving deployment, idempotently.

        Called from read_status on each poll once the sandbox is READY: launch the
        detached serve command (once, guarded by a marker file) and expose its ports.
        Provisioning thus happens across reconcile cycles instead of blocking create.
        On a provisioning failure the sandbox is deleted so it does not leak behind a
        terminal FAILED deployment.
        """
        sandbox_id = sandbox.metadata.id or sandbox_nm

        # Fast path: ports already exposed on a prior poll -> the deployment is serving,
        # as long as the workload is alive. An exposed service proves routing, not health.
        endpoints = await self._list_endpoints(sandbox_nm)
        if endpoints:
            failure = await self._serve_failure(sandbox_id)
            if failure is not None:
                return failure
            return BackendStatusUpdate(status="READY", status_message="Sandbox serving", endpoints=endpoints)

        config_name = dict(sandbox.metadata.labels).get(CONFIG_NAME_LABEL)
        if not config_name:
            return BackendStatusUpdate(status="FAILED", status_message="Sandbox is missing its deployment-config label")
        try:
            config = await self._load_deployment_config(workspace, config_name)
        except Exception as exc:
            return BackendStatusUpdate(status="FAILED", status_message=f"Failed to load deployment config: {exc}")
        container = config.containers[0]

        # Launch the serve command once; the launcher writes a marker so a later poll
        # does not relaunch it (read_status keeps no state across calls).
        if not await self._serve_launched(sandbox_id):
            failure = await self._launch_serve(sandbox_id, list(container.command) + list(container.args))
            if failure is not None:
                await self._delete_sandbox_best_effort(sandbox_nm)
                return failure
            return BackendStatusUpdate(status="STARTING", status_message="Serve command launched")

        # Never expose a port to a workload that is not demonstrably running. The launch
        # marker only proves the launcher shell accepted the `&`, so a live pid is what
        # stops a launch that started nothing from advancing to READY.
        state = await self._serve_state(sandbox_id)
        if state == "dead":
            return await self._serve_dead_update(sandbox_id)
        if state == "pending":
            return BackendStatusUpdate(status="STARTING", status_message="Serve launched; awaiting serve pid")

        # Serve launched but ports not yet exposed: expose them.
        try:
            endpoints = await self._expose_ports(sandbox_nm, container)
        except grpc.RpcError as exc:
            await self._delete_sandbox_best_effort(sandbox_nm)
            return BackendStatusUpdate(status="FAILED", status_message=f"ExposeService failed: {_rpc_detail(exc)}")
        if not endpoints:
            return BackendStatusUpdate(status="STARTING", status_message="Serve launched; awaiting endpoints")
        return BackendStatusUpdate(status="READY", status_message="Sandbox serving", endpoints=endpoints)

    async def _serve_launched(self, sandbox_id: str) -> bool:
        """Whether the serve command has already been launched (marker file present)."""
        exit_code, _ = await self._exec_detached(sandbox_id, ["/bin/sh", "-lc", f"test -f {_LAUNCH_MARKER}"])
        return exit_code == 0

    async def _serve_state(self, sandbox_id: str) -> Literal["alive", "dead", "pending"]:
        """Whether the serve process is running, known dead, or not yet accounted for.

        Only a probe that positively proves death reports ``dead``, so a flaky exec RPC
        or an unreadable marker never flaps a healthy deployment. Everything undecided is
        ``pending``, which callers treat as "not yet safe to expose".
        """
        exit_code, _ = await self._exec_detached(sandbox_id, ["/bin/sh", "-lc", _LIVENESS_PROBE])
        if exit_code == _SERVE_DEAD_EXIT:
            return "dead"
        if exit_code in (None, 0):
            return "alive"
        return "pending"

    async def _serve_dead_update(self, sandbox_id: str) -> BackendStatusUpdate:
        """A FAILED update carrying the workload's own last output.

        The sandbox is kept (unlike the provisioning-failure paths) so its log stays
        readable through ``get_logs``.
        """
        tail = await self._serve_log_tail(sandbox_id)
        message = "Serve process exited; deployment is not serving"
        if tail:
            message = f"{message}. Last output: {tail}"
        return BackendStatusUpdate(status="FAILED", status_message=message)

    async def _serve_failure(self, sandbox_id: str) -> BackendStatusUpdate | None:
        """A FAILED update when the serve process is known dead, else None.

        Used where the deployment is already serving, so only positive evidence of death
        demotes it; a pending probe leaves it alone.
        """
        if await self._serve_state(sandbox_id) != "dead":
            return None
        return await self._serve_dead_update(sandbox_id)

    async def _serve_log_tail(self, sandbox_id: str, lines: int = _LOG_TAIL_LINES) -> str:
        """Last lines of the workload log, or "" when it cannot be read."""
        try:
            exit_code, output = await self._exec_detached(
                sandbox_id, ["/bin/sh", "-lc", f"tail -n {int(lines)} {_SERVE_LOG}"]
            )
        except grpc.RpcError:
            logger.warning("Failed to read the serve log for sandbox %s", sandbox_id, exc_info=True)
            return ""
        return output.strip() if exit_code in (None, 0) else ""

    async def _launch_serve(self, sandbox_id: str, serve_command: list[str]) -> BackendStatusUpdate | None:
        """Launch the detached serve command, writing the launch marker on success.

        Returns None on success, or a FAILED update if the launcher itself failed (bad
        workdir/shell or a non-zero launcher exit). The backgrounded serve process is
        not supervised, so this catches launch-time failures, not later serve crashes.
        """
        serve = shlex.join(serve_command)
        # The inner shell records its own pid and then execs, so the pidfile holds the
        # workload's pid whether or not setsid forks. The marker is written synchronously
        # so a poll racing the background start does not relaunch, and holds the launch
        # time so the probe can age out a pidfile that never appears.
        inner = f"echo $$ >{_SERVE_PIDFILE}; exec {serve} >{_SERVE_LOG} 2>&1"
        launch = f"setsid /bin/sh -c {shlex.quote(inner)} </dev/null >/dev/null 2>&1 & date +%s >{_LAUNCH_MARKER}"
        workdir = self._executor_config.serve_workdir
        if workdir:
            launch = f"cd {shlex.quote(workdir)} && {launch}"
        try:
            exit_code, output = await self._exec_detached(sandbox_id, ["/bin/sh", "-lc", launch])
        except grpc.RpcError as exc:
            return BackendStatusUpdate(
                status="FAILED", status_message=f"Failed to launch serve command: {_rpc_detail(exc)}"
            )
        if exit_code not in (None, 0):
            detail = output.strip()
            message = f"Serve command launch exited with code {exit_code}"
            if detail:
                message = f"{message}: {detail}"
            return BackendStatusUpdate(status="FAILED", status_message=message)
        return None

    async def _delete_sandbox_best_effort(self, sandbox_nm: str) -> None:
        """Best-effort DeleteSandbox to avoid leaking a partially-provisioned sandbox.

        Swallows all errors (including a NOT_FOUND, which makes this idempotent) so a
        cleanup failure never masks the original provisioning failure.
        """
        try:
            await self._unary(self._stub.DeleteSandbox, pb.DeleteSandboxRequest(name=sandbox_nm))
        except Exception:
            logger.warning("Failed to clean up sandbox %s after provisioning failure", sandbox_nm, exc_info=True)

    async def _try_get_sandbox(self, sandbox_nm: str) -> Any | None:
        try:
            response = await self._unary(self._stub.GetSandbox, pb.GetSandboxRequest(name=sandbox_nm))
        except grpc.RpcError as exc:
            if _rpc_code(exc) == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return response.sandbox

    async def _exec_detached(self, sandbox_id: str, command: list[str]) -> tuple[int | None, str]:
        """Run a command, draining its event stream. Returns (exit_code, combined output)."""
        timeout = self._executor_config.request_timeout_seconds
        request = pb.ExecSandboxRequest(sandbox_id=sandbox_id, command=command, timeout_seconds=timeout)

        def _drain() -> tuple[int | None, str]:
            exit_code: int | None = None
            chunks: list[str] = []
            for event in self._stub.ExecSandbox(request, timeout=timeout):
                if event.HasField("stdout"):
                    chunks.append(event.stdout.data.decode("utf-8", errors="replace"))
                elif event.HasField("stderr"):
                    chunks.append(event.stderr.data.decode("utf-8", errors="replace"))
                elif event.HasField("exit"):
                    exit_code = event.exit.exit_code
            return exit_code, "".join(chunks)

        return await asyncio.to_thread(_drain)

    async def _list_endpoints(self, sandbox_nm: str) -> list[Endpoint]:
        """Return the sandbox's currently exposed services as endpoints."""
        try:
            response = await self._unary(self._stub.ListServices, pb.ListServicesRequest(sandbox=sandbox_nm))
        except grpc.RpcError:
            logger.warning("Failed to list services for sandbox %s", sandbox_nm, exc_info=True)
            return []
        return [Endpoint(name=svc.endpoint.service_name, url=svc.url, protocol="http") for svc in response.services]

    async def _expose_ports(self, sandbox_nm: str, container: Container) -> list[Endpoint]:
        endpoints: list[Endpoint] = []
        for port in container.ports:
            service = _service_name(port)
            request = pb.ExposeServiceRequest(
                sandbox=sandbox_nm,
                service=service,
                target_port=port.container_port,
            )
            response = await self._unary(self._stub.ExposeService, request)
            endpoints.append(Endpoint(name=service, url=response.url, protocol="http"))
        return endpoints


def _sandbox_name(workspace: str, name: str) -> str:
    """OpenShell sandbox name, within ``_MAX_ROUTABLE_NAME_LEN``.

    The limit rules out the shared ``dep-<ws>-<name>-<hash>`` scheme, so the human-readable
    workspace/name mapping is carried in identity labels (used by list/idempotency) instead.

    The digest is a non-crypto short id; the length is chosen to fit the routable-name limit.
    """
    digest = hashlib.sha256(f"{workspace}/{name}".encode()).hexdigest()[:14]
    return f"nmp-{digest}"


def _service_name(port: Any) -> str:
    """Routable service name for a container port, within ``_MAX_ROUTABLE_NAME_LEN``.

    Port names are author-supplied, so an over-long one is truncated with a digest suffix:
    the digest keeps distinct names distinct, and avoids the trailing ``-`` a bare
    truncation can leave behind (invalid as a DNS label).
    """
    raw = port.name or f"port-{port.container_port}"
    if len(raw) <= _MAX_ROUTABLE_NAME_LEN:
        return raw
    digest = hashlib.sha256(raw.encode()).hexdigest()[:6]
    prefix = raw[: _MAX_ROUTABLE_NAME_LEN - len(digest) - 1].rstrip("-")
    return f"{prefix}-{digest}"


def _sandbox_matches(sandbox: Any, workspace: str, name: str) -> bool:
    sandbox_labels = dict(sandbox.metadata.labels)
    return (
        sandbox_labels.get(MANAGED_BY_KEY) == MANAGED_BY_LABEL
        and sandbox_labels.get(DEPLOYMENT_WORKSPACE_LABEL) == workspace
        and sandbox_labels.get(DEPLOYMENT_NAME_LABEL) == name
    )


def _condition_message(status: Any) -> str:
    for condition in reversed(status.conditions):
        if condition.message:
            return condition.message
    return ""


def _format_log_line(line: Any) -> str:
    source = getattr(line, "source", "")
    message = getattr(line, "message", "") or getattr(line, "line", "")
    return f"[{source}] {message}".strip() if source else str(message)


def _rpc_code(exc: grpc.RpcError) -> grpc.StatusCode | None:
    getter = getattr(exc, "code", None)
    if not callable(getter):
        return None
    return cast("grpc.StatusCode", getter())


def _rpc_detail(exc: grpc.RpcError) -> str:
    code = _rpc_code(exc)
    details_getter = getattr(exc, "details", None)
    details = details_getter() if callable(details_getter) else str(exc)
    return f"{code.name if code is not None else 'UNKNOWN'}: {details}"


def _read_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    with open(path, "rb") as handle:
        return handle.read()
