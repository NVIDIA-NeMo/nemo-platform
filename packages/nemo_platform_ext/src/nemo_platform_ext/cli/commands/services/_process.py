# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local process lifecycle for ``nemo services``.

Uses per-instance scoped directories under ``$XDG_STATE_HOME/nmp/instances/``
with flock-based liveness tracking.  Each instance directory contains:

- ``services.lock`` -- exclusive flock held for the process lifetime
- ``instance.json``  -- descriptor with PID, port, services, etc.
- ``services.log``   -- stdout/stderr log (background mode)

The flock is the **source of truth** for whether an instance is alive.
The descriptor is metadata used by ``status``, ``ls``, and ``restart``.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import psutil
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LOCK_FILENAME = "services.lock"
DESCRIPTOR_FILENAME = "instance.json"
LOG_FILENAME = "services.log"

DEFAULT_SERVICES_BIND_HOST = "127.0.0.1"
SUGGESTED_ALT_PORT = 9090

_SIGTERM_POLL_INTERVAL = 0.25
_DEFAULT_STOP_TIMEOUT = 30.0


def _pause(seconds: float) -> None:
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# State directory layout
# ---------------------------------------------------------------------------


def _base_state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "nmp"
    return Path.home() / ".local" / "state" / "nmp"


def _instances_dir(*, base_dir: Path | None = None) -> Path:
    return (base_dir or _base_state_dir()) / "instances"


def _find_git_root() -> str:
    """Walk up from cwd looking for a ``.git`` directory.  Falls back to cwd."""
    cur = Path.cwd().resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return str(parent)
    return str(cur)


_scope_prefix_cache: str | None = None


_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_scope(scope: str) -> str:
    """Ensure *scope* is safe to use as a directory name."""
    if not _SCOPE_RE.fullmatch(scope):
        raise ValueError(f"Invalid instance scope: {scope!r}")
    return scope


def compute_scope(*, port: int, instance_name: str | None = None) -> str:
    """Compute a scope identifier for this working directory + port.

    Default: ``sha1(git_toplevel_or_cwd)[:8]-<port>``.
    Override with an explicit *instance_name*.
    """
    if instance_name:
        return _validate_scope(instance_name)
    global _scope_prefix_cache  # noqa: PLW0603
    if _scope_prefix_cache is None:
        root = _find_git_root()
        _scope_prefix_cache = hashlib.sha1(root.encode()).hexdigest()[:8]  # noqa: S324
    return f"{_scope_prefix_cache}-{port}"


def instance_dir(scope: str, *, base_dir: Path | None = None) -> Path:
    d = _instances_dir(base_dir=base_dir) / _validate_scope(scope)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# flock-based liveness
# ---------------------------------------------------------------------------


def acquire_lock(scope: str, *, base_dir: Path | None = None) -> int:
    """Acquire an exclusive flock for *scope*.  Returns the open fd.

    Raises ``InstanceAlreadyRunningError`` if the lock is already held.
    The caller must keep the fd open for the process lifetime.
    """
    d = instance_dir(scope, base_dir=base_dir)
    lock_path = d / LOCK_FILENAME
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as err:
        os.close(fd)
        if err.errno in {errno.EACCES, errno.EAGAIN}:
            raise InstanceAlreadyRunningError(scope) from err
        raise
    return fd


def is_instance_alive(scope: str, *, base_dir: Path | None = None) -> bool:
    """Check if an instance is alive by probing its flock."""
    d = _instances_dir(base_dir=base_dir) / scope
    lock_path = d / LOCK_FILENAME
    if not lock_path.exists():
        return False
    fd = -1
    try:
        fd = os.open(str(lock_path), os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except FileNotFoundError:
        return False
    except OSError:
        return True
    finally:
        if fd >= 0:
            os.close(fd)


class InstanceAlreadyRunningError(Exception):
    def __init__(self, scope: str) -> None:
        self.scope = scope
        super().__init__(f"Instance '{scope}' is already running")


class ForegroundInstanceError(Exception):
    """Raised when ``stop`` targets a foreground instance without ``--force``."""

    def __init__(self, scope: str, pid: int) -> None:
        self.scope = scope
        self.pid = pid
        super().__init__(
            f"Instance '{scope}' (pid {pid}) is running in the foreground. "
            "Use Ctrl-C in its terminal to stop it, or pass --force."
        )


# ---------------------------------------------------------------------------
# Port availability (preflight before bind)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortConflict:
    """Structured port conflict for terminal rendering by CLI callers."""

    kind: Literal["foreign", "nemo_instance"]
    port: int
    scope: str | None = None


def _normalize_bind_host(host: str) -> str:
    """Normalize bind hosts for descriptor comparison."""
    if host == "localhost":
        return "127.0.0.1"
    return host


def _instance_owns_listener(
    scope: str,
    host: str,
    port: int,
    *,
    base_dir: Path | None = None,
) -> bool:
    """Return True when a live instance for *scope* is bound to *host*:*port*."""
    if not is_instance_alive(scope, base_dir=base_dir):
        return False
    desc = read_descriptor(scope, base_dir=base_dir)
    if desc is None:
        return False
    return desc.port == port and _normalize_bind_host(desc.host) == _normalize_bind_host(host)


def is_port_bindable(host: str, port: int) -> bool:
    """Return True if *host*:*port* can be bound on at least one address family.

    Uses ``getaddrinfo`` so IPv4 and IPv6 hosts (for example ``::``) are probed
    with the correct socket family instead of always using ``AF_INET``.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE)
    except OSError:
        return False
    if not infos:
        return False
    for family, socktype, proto, _, sockaddr in infos:
        with contextlib.suppress(OSError):
            with socket.socket(family, socktype, proto) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(sockaddr)  # noqa: S104  # nosec B104
            return True
    return False


def check_port_available_for_start(
    host: str,
    port: int,
    scope: str,
    *,
    base_dir: Path | None = None,
) -> PortConflict | None:
    """Return conflict info when *port* cannot be bound, else None.

    Classifies conflicts as ``nemo_instance`` only when a live instance for
    *scope* is recorded on the same host and port. Otherwise reports ``foreign``.
    Does not log or print — callers render to the terminal.
    """
    if is_port_bindable(host, port):
        return None
    if _instance_owns_listener(scope, host, port, base_dir=base_dir):
        return PortConflict(kind="nemo_instance", port=port, scope=scope)
    return PortConflict(kind="foreign", port=port)


def format_port_conflict(err: PortConflict) -> list[str]:
    """Return actionable message lines for terminal display.

    Message text depends on ``err.kind`` (foreign process vs NeMo instance).
    """
    if err.kind == "nemo_instance":
        return [
            f"Port {err.port} is in use by a NeMo Platform instance for this directory.",
            "Stop it first with: nemo services stop",
            "Or restart with:    nemo services restart",
        ]
    return [
        f"Port {err.port} is already in use by another process.",
        "Free the port or choose a different one:",
        f"lsof -i :{err.port}          (see what's listening)",
        f"nemo services run --port {SUGGESTED_ALT_PORT}",
    ]


# ---------------------------------------------------------------------------
# Descriptor (instance.json)
# ---------------------------------------------------------------------------


class InstanceDescriptor(BaseModel):
    pid: int
    scope: str
    host: str = "127.0.0.1"
    port: int = 8080
    mode: Literal["foreground", "background"] = "background"
    create_time: float = 0.0
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    services: list[str] | None = None
    controllers: list[str] | None = None
    service_group: str | None = None
    controller_group: str | None = None
    sidecars: list[str] | None = None
    config_path: str | None = None
    log_path: str | None = None


def write_descriptor(desc: InstanceDescriptor, *, base_dir: Path | None = None) -> Path:
    d = instance_dir(desc.scope, base_dir=base_dir)
    path = d / DESCRIPTOR_FILENAME
    payload = desc.model_dump()
    fd, tmp = tempfile.mkstemp(dir=str(d), suffix=".tmp")
    try:
        os.write(fd, (json.dumps(payload, indent=2) + "\n").encode())
        os.close(fd)
        fd = -1
        os.replace(tmp, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def read_descriptor(scope: str, *, base_dir: Path | None = None) -> InstanceDescriptor | None:
    d = _instances_dir(base_dir=base_dir) / scope
    path = d / DESCRIPTOR_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return InstanceDescriptor.model_validate(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.debug("Corrupt descriptor at %s, ignoring", path, exc_info=True)
        return None


def remove_descriptor(scope: str, *, base_dir: Path | None = None) -> None:
    d = _instances_dir(base_dir=base_dir) / scope
    path = d / DESCRIPTOR_FILENAME
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not remove descriptor %s", path, exc_info=True)


# ---------------------------------------------------------------------------
# PID validation via psutil
# ---------------------------------------------------------------------------


def validate_pid(pid: int, expected_create_time: float, *, tolerance: float = 2.0) -> bool:
    """Check that *pid* is alive and its create_time matches the recorded value.

    The *tolerance* accounts for float precision across platforms.
    """
    try:
        proc = psutil.Process(pid)
        return abs(proc.create_time() - expected_create_time) < tolerance
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def get_create_time(pid: int) -> float:
    """Return the create_time for *pid*.  Raises if the process doesn't exist."""
    return psutil.Process(pid).create_time()


# ---------------------------------------------------------------------------
# Instance listing
# ---------------------------------------------------------------------------


@dataclass
class InstanceInfo:
    scope: str
    alive: bool
    descriptor: InstanceDescriptor | None


def list_instances(*, base_dir: Path | None = None) -> list[InstanceInfo]:
    """Scan all instance directories and return their status.

    Side effect: removes stale descriptors for dead instances so that
    subsequent calls (and ``ls`` output) don't show ghost entries.
    """
    idir = _instances_dir(base_dir=base_dir)
    if not idir.exists():
        return []
    results: list[InstanceInfo] = []
    for child in sorted(idir.iterdir()):
        if not child.is_dir():
            continue
        scope = child.name
        alive = is_instance_alive(scope, base_dir=base_dir)
        desc = read_descriptor(scope, base_dir=base_dir)
        if not alive and desc is not None:
            remove_descriptor(scope, base_dir=base_dir)
            desc = None
        results.append(InstanceInfo(scope=scope, alive=alive, descriptor=desc))
    return results


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------


def rotate_log(scope: str, *, base_dir: Path | None = None) -> Path:
    """Rotate the existing log and return the path for the new one."""
    d = instance_dir(scope, base_dir=base_dir)
    log_path = d / LOG_FILENAME
    if log_path.exists() and log_path.stat().st_size > 0:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        rotated = d / f"{LOG_FILENAME}.{ts}"
        log_path.rename(rotated)
    return log_path


def log_path_for(scope: str, *, base_dir: Path | None = None) -> Path:
    return instance_dir(scope, base_dir=base_dir) / LOG_FILENAME


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


@dataclass
class StopResult:
    stopped_pids: list[int]
    swept_children: list[int] = field(default_factory=list)


def _snapshot_children(pid: int) -> list[psutil.Process]:
    """Return all descendant processes of *pid*.

    Must be called while the parent is still alive; once it exits,
    children are reparented to init and won't appear in the tree.
    """
    try:
        return psutil.Process(pid).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


def _sweep_orphans(children: list[psutil.Process], timeout: float = 5.0) -> list[int]:
    """Terminate any still-alive processes from a prior snapshot.

    Sends SIGTERM, waits up to *timeout*, then SIGKILL survivors.
    Returns PIDs that were signaled.  Handles ``NoSuchProcess`` gracefully
    since children may have already exited during graceful shutdown.
    """
    alive_children = [c for c in children if c.is_running()]
    if not alive_children:
        return []

    killed: list[int] = []
    for child in alive_children:
        try:
            child.terminate()
            killed.append(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # Already exited or not owned by us — skip.

    _, still_alive = psutil.wait_procs(alive_children, timeout=timeout)
    for child in still_alive:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # Raced with exit or not owned — nothing to do.

    if killed:
        logger.info(
            "Swept %d orphaned child %s: %s", len(killed), "process" if len(killed) == 1 else "processes", killed
        )

    return killed


def stop_instance(
    scope: str,
    *,
    base_dir: Path | None = None,
    timeout: float = _DEFAULT_STOP_TIMEOUT,
    force: bool = False,
) -> StopResult:
    """Stop a running instance by scope.

    Uses the flock and descriptor to find the process.  If the flock is held,
    the instance is definitely alive.  If the flock is not held but a
    descriptor exists with a validated PID, we still attempt to stop (handles
    edge cases where the process outlives the flock probe window).

    Foreground instances (``mode="foreground"``) are protected: they must be
    stopped via Ctrl-C in their own terminal.  Pass *force=True* to override.

    Sends SIGTERM, waits up to *timeout* seconds, then escalates to SIGKILL.
    After the parent exits, any surviving child processes (e.g. agent
    deployments) are swept up via SIGTERM/SIGKILL.
    """
    desc = read_descriptor(scope, base_dir=base_dir)
    alive = is_instance_alive(scope, base_dir=base_dir)

    if not alive and desc is None:
        return StopResult(stopped_pids=[])

    if desc is None:
        return StopResult(stopped_pids=[])

    if desc.mode == "foreground" and not force:
        raise ForegroundInstanceError(scope, desc.pid)

    pid = desc.pid
    if not validate_pid(pid, desc.create_time):
        logger.debug("PID %d doesn't match recorded create_time, cleaning up descriptor", pid)
        remove_descriptor(scope, base_dir=base_dir)
        return StopResult(stopped_pids=[])

    # Snapshot child tree while parent is alive — children are reparented to
    # init once the parent exits, making them invisible to psutil afterwards.
    children = _snapshot_children(pid)

    try:
        os.kill(pid, signal.SIGTERM)
        logger.debug("Sent SIGTERM to pid %d", pid)
    except OSError:
        logger.debug("Failed to send SIGTERM to pid %d", pid, exc_info=True)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            break
        _pause(_SIGTERM_POLL_INTERVAL)
    else:
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                logger.debug("Sent SIGKILL to pid %d", pid)
            except PermissionError:
                logger.warning("No permission to SIGKILL pid %d; process may still be running", pid)
                swept = _sweep_orphans(children) if children else []
                # Keep the descriptor so subsequent stop/restart can retry.
                return StopResult(stopped_pids=[], swept_children=swept)
            except OSError:
                logger.debug("Failed to send SIGKILL to pid %d", pid, exc_info=True)

    swept = _sweep_orphans(children) if children else []

    remove_descriptor(scope, base_dir=base_dir)
    return StopResult(stopped_pids=[pid], swept_children=swept)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Background start
# ---------------------------------------------------------------------------


def start_background(
    *,
    scope: str,
    services: list[str] | None = None,
    service_group: str | None = None,
    controllers: list[str] | None = None,
    controller_group: str | None = None,
    sidecars: list[str] | None = None,
    config_path: str | None = None,
    host: str = DEFAULT_SERVICES_BIND_HOST,
    port: int = 8080,
    base_dir: Path | None = None,
    data_dir: str | None = None,
) -> subprocess.Popen:
    """Launch ``nemo services run`` as a detached background subprocess.

    The child acquires the flock and writes its own descriptor.  The parent
    returns the ``Popen`` handle for health polling.
    """
    log_file_path = rotate_log(scope, base_dir=base_dir)
    log_file = open(log_file_path, "a")  # noqa: SIM115

    nemo_bin = str(Path(sys.executable).parent / "nemo")
    args: list[str] = [nemo_bin, "services", "run"]
    if services:
        args += ["--services", ",".join(services)]
    if service_group:
        args += ["--service-group", service_group]
    if controllers:
        args += ["--controllers", ",".join(controllers)]
    if controller_group:
        args += ["--controller-group", controller_group]
    if sidecars:
        args += ["--sidecars", ",".join(sidecars)]
    if config_path:
        args += ["--config", config_path]
    args += ["--host", host, "--port", str(port)]
    args += ["--instance", scope]

    env = os.environ.copy()
    if data_dir and "NMP_DATA_DIR" not in env:
        env["NMP_DATA_DIR"] = data_dir
    if base_dir:
        env["_NMP_STATE_DIR"] = str(base_dir)
    # Tell the child ``run`` process it was launched by ``start`` so it
    # records mode="background" in its descriptor.  This is internal
    # parent-to-child signaling -- not a public API surface -- following the
    # same convention as _NMP_STATE_DIR above.
    env["_NMP_LAUNCH_MODE"] = "background"

    try:
        proc = subprocess.Popen(
            args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        log_file.close()
        raise
    log_file.close()
    logger.debug("Started services (pid=%d), log=%s", proc.pid, log_file_path)
    return proc
