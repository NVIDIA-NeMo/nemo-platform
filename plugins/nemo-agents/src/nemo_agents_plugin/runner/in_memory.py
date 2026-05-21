# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""InMemoryRunnerBackend — spawns ``nat serve`` subprocesses for agent deployments.

This is the initial backend implementation.  Agent processes run as local
subprocesses on the same machine as the platform server.  Process state is
tracked in memory; it is lost if the platform restarts (orphaned processes
must be cleaned up manually or via OS process management).

Future backends (DockerRunnerBackend, K8sRunnerBackend) will replace this for
production deployments.

Module-level helpers ``system_dir_for_workspace`` and ``log_path_for_deployment``
encode the on-disk layout convention so out-of-process callers (e.g. the
``nemo agents logs`` CLI) can locate a deployment's log file without
instantiating the backend.  The convention is intentionally narrow: it is
correct only for the local in-memory backend on the same host.  Once a
remote backend (Docker/K8s) lands, log retrieval should move to a server-
side endpoint that streams content over HTTP.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import httpx
import yaml
from nemo_agents_plugin.config import AgentsConfig, ControllerConfig
from nemo_agents_plugin.runner.backend import DeploymentInfo, RunnerBackend

# Match characters not safe for filesystem paths.  Deployment names are
# normally URL-safe identifiers, but we sanitise defensively to ensure we
# never spawn temp files outside the system dir.
_FILENAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_filename(name: str) -> str:
    """Coerce a deployment name into a safe single filename component.

    Replaces filesystem-unsafe characters with ``_`` and falls back to
    ``"deployment"`` if the result strips to empty.  Collision-safe so long
    as the agents API enforces URL-safe deployment names upstream (which it
    currently does — names that differ only by unsafe characters cannot
    coexist).
    """
    cleaned = _FILENAME_UNSAFE_RE.sub("_", name).strip("._-") or "deployment"
    return cleaned


def system_dir(workspace_dir: Path | None = None) -> Path:
    """Return the directory holding rendered configs and per-deployment logs.

    When *workspace_dir* is omitted, the default is read from
    :class:`AgentsConfig` so out-of-process callers (CLI) resolve the same
    path the running platform uses.
    """
    if workspace_dir is None:
        workspace_dir = AgentsConfig.get().controller.workspace_dir
    return workspace_dir.resolve() / "system"


def log_path_for_deployment(name: str, workspace_dir: Path | None = None) -> Path:
    """Return the absolute log-file path for a deployment named *name*.

    Path is deterministic: ``<system_dir>/<sanitized-name>.log``.  Callers
    outside the runner backend (e.g. the ``nemo agents logs`` CLI) can use
    this helper to locate a deployment's log without instantiating the
    backend or consulting in-process state.
    """
    return system_dir(workspace_dir) / f"{_sanitize_filename(name)}.log"


def config_path_for_deployment(name: str, workspace_dir: Path | None = None) -> Path:
    """Return the absolute rendered-config path for a deployment named *name*."""
    return system_dir(workspace_dir) / f"{_sanitize_filename(name)}.yaml"


logger = logging.getLogger(__name__)


class InMemoryRunnerBackend(RunnerBackend):
    """Manages agent processes as local subprocesses.

    Process state is stored in instance-level dicts.  All public methods are
    async; blocking subprocess calls are dispatched via ``asyncio.to_thread``
    to avoid blocking the event loop.
    """

    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._workspace_root: Path = config.workspace_dir.resolve()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._deployments: dict[str, DeploymentInfo] = {}
        self._next_port: int = config.port_range_start
        self._temp_files: dict[str, Path] = {}
        self._http_client: httpx.AsyncClient | None = None

    @property
    def output_base_dir(self) -> Path:
        """Backend artifact root: ``workspace_dir`` itself (configs/logs live in ``system/``).

        Defaults to ``nmp_user_data_dir() / "agents"`` (e.g.
        ``~/.local/share/nemo/agents``) so artifacts persist across reboots
        and live in a documented, user-accessible location instead of inside
        the plugin source tree.
        """
        return self._workspace_root

    @property
    def system_dir(self) -> Path:
        """Directory under ``output_base_dir`` for rendered configs and log files."""
        return system_dir(self._workspace_root)

    def log_path_for(self, name: str) -> Path:
        """Instance-level convenience wrapper around :func:`log_path_for_deployment`."""
        return log_path_for_deployment(name, self._workspace_root)

    def config_path_for(self, name: str) -> Path:
        """Instance-level convenience wrapper around :func:`config_path_for_deployment`."""
        return config_path_for_deployment(name, self._workspace_root)

    def allocate_port(self) -> int:
        """Return the next free port in [port_range_start, port_range_end].

        Scans forward from the current position, wrapping around, and probes
        each candidate with ``socket.bind`` to confirm it is not already in
        use.  This handles restarts with orphaned processes, third-party
        processes occupying ports in the range, and reuse of ports freed by
        deleted deployments.

        Raises:
            RuntimeError: If no free port is found in the entire range.
        """
        start = self._config.port_range_start
        end = self._config.port_range_end
        span = end - start + 1
        for offset in range(span):
            candidate = start + (self._next_port - start + offset) % span
            if self._is_port_free(candidate):
                self._next_port = candidate + 1 if candidate < end else start
                return candidate
        raise RuntimeError(
            f"No free port available in range [{start}, {end}]. "
            "Consider adjusting NMP_AGENTS_CONTROLLER_PORT_RANGE_START / _END."
        )

    @staticmethod
    def _is_port_free(port: int) -> bool:
        """Return ``True`` if nothing is currently bound to *port* on loopback."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    async def create_deployment(self, name: str, config: dict[str, Any], port: int) -> DeploymentInfo:
        """Write config to a deterministic file and spawn ``nat serve``."""
        config_path = await asyncio.to_thread(self._write_config, name, config)
        log_path = self.log_path_for(name)
        try:
            proc = await asyncio.to_thread(self._spawn, name, config_path, log_path, port)
        except Exception:
            config_path.unlink(missing_ok=True)
            raise

        info = DeploymentInfo(
            name=name,
            status="starting",
            port=port,
            pid=proc.pid,
            endpoint=f"http://127.0.0.1:{port}",
            log_path=str(log_path),
        )
        self._processes[name] = proc
        self._deployments[name] = info
        self._temp_files[name] = config_path
        logger.info(
            "Spawned agent process for '%s' (pid=%d, port=%d, log=%s)",
            name,
            proc.pid,
            port,
            log_path,
        )
        return info

    async def get_deployment_status(self, name: str) -> DeploymentInfo | None:
        info = self._deployments.get(name)
        if info is None:
            return None
        proc = self._processes.get(name)
        if proc is not None and proc.poll() is not None:
            info.status = "failed"
            # Surface the exit code so operators can correlate with the log.
            # ``returncode`` is negative when killed by a signal (-N == SIGN).
            info.error = f"Process exited with code {proc.returncode}"
        return info

    async def delete_deployment(self, name: str) -> bool:
        proc = self._processes.pop(name, None)
        info = self._deployments.pop(name, None)
        config_path = self._temp_files.pop(name, None)

        if proc is None and info is None:
            return False

        if proc is not None:
            await asyncio.to_thread(self._terminate, name, proc)

        if config_path is not None:
            config_path.unlink(missing_ok=True)

        logger.info("Deleted agent deployment '%s'", name)
        return True

    async def list_deployments(self) -> list[DeploymentInfo]:
        return list(self._deployments.values())

    async def health_check(self, endpoint: str) -> bool:
        url = endpoint.rstrip("/") + "/health"
        try:
            client = self._get_http_client()
            resp = await client.get(url)
            return resp.status_code < 400
        except Exception:
            return False

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=5.0)
        return self._http_client

    async def shutdown(self) -> None:
        """Terminate all managed processes (best-effort)."""
        names = list(self._processes.keys())
        results = await asyncio.gather(
            *(asyncio.to_thread(self._terminate, name, proc) for name, proc in list(self._processes.items())),
            return_exceptions=True,
        )
        for name, result in zip(names, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("Error terminating '%s' during shutdown", name, exc_info=result)
        self._processes.clear()
        self._deployments.clear()
        for path in self._temp_files.values():
            path.unlink(missing_ok=True)
        self._temp_files.clear()
        if self._http_client is not None and not self._http_client.is_closed:
            try:
                await self._http_client.aclose()
            except Exception:
                logger.warning("Error closing HTTP client during shutdown", exc_info=True)
            self._http_client = None
        logger.info("InMemoryRunnerBackend shut down — all processes terminated.")

    def _write_config(self, name: str, config: dict[str, Any]) -> Path:
        """Write the rendered NAT config to a deterministic per-deployment path.

        Earlier versions used ``tempfile.NamedTemporaryFile`` with a random
        suffix, which made the matching ``.log`` file impossible to locate
        without scanning a directory.  We now use ``<system_dir>/<name>.yaml``
        so the log path is predictable and exposed to the controller as
        ``DeploymentInfo.log_path``.
        """
        system_dir = self.system_dir
        system_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.config_path_for(name)
        # Write atomically: serialise to a sibling temp path then rename in
        # case a previous run left a stale file behind.
        tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(config, fh)
        tmp_path.replace(config_path)
        return config_path

    def _spawn(
        self,
        name: str,
        config_path: Path,
        log_path: Path,
        port: int,
    ) -> subprocess.Popen[bytes]:
        """Spawn ``nat start fastapi`` bound to 127.0.0.1 (platform-internal only).

        ``--host`` is intentionally omitted: processes bind to the default
        (127.0.0.1) so they are not directly reachable externally.  All
        traffic reaches them through the agents gateway proxy.
        """
        # config_path is an absolute path — pass it as-is so nat can find it
        # regardless of the working directory it inherits.
        nat_bin = shutil.which("nat") or "/app/.venv/bin/nat"
        cmd = [
            nat_bin,
            "start",
            "fastapi",
            "--config_file",
            str(config_path),
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Spawning: %s  (log: %s)", " ".join(cmd), log_path)
        log_file = log_path.open("w")
        try:
            return subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        finally:
            # Parent closes its copy of the fd; the child retains its inherited
            # copy for the lifetime of the subprocess.
            log_file.close()

    def _terminate(self, name: str, proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        logger.debug("Terminated process for '%s' (pid=%d)", name, proc.pid)
