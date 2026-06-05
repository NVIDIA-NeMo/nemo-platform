# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, NoReturn

import httpx
import typer
from nemo_platform_ext.cli.commands.services._process import (
    ForegroundInstanceError,
    InstanceAlreadyRunningError,
    InstanceDescriptor,
    PortConflict,
    acquire_lock,
    check_port_available_for_start,
    compute_scope,
    format_port_conflict,
    get_create_time,
    is_instance_alive,
    list_instances,
    log_path_for,
    read_descriptor,
    remove_descriptor,
    start_background,
    stop_instance,
    write_descriptor,
)
from nemo_platform_ext.cli.core.help_formatter import create_typer_app

logger = logging.getLogger(__name__)

services_app = create_typer_app(name="services", help="Run platform services locally.")

_HEALTH_TIMEOUT_SECONDS = 60
_HEALTH_POLL_INTERVAL = 2.0
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080
_DEFAULT_STOP_TIMEOUT = 30.0


@services_app.callback(invoke_without_command=True)
def services_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        base_dir_str = _effective_base_dir()
        base_dir = Path(base_dir_str) if base_dir_str else None
        running = [i for i in list_instances(base_dir=base_dir) if i.alive and i.descriptor]
        for info in running:
            desc = info.descriptor
            assert desc is not None
            typer.echo(f"\nRunning: {info.scope} (pid {desc.pid}, {desc.host}:{desc.port}, {desc.mode})")


def _require_services_extra() -> None:
    """Ensure the ``[all]`` extra (e.g. ``pyleak``) is installed."""
    if importlib.util.find_spec("pyleak") is not None:
        return
    typer.echo(
        "Running local platform services needs extra components that aren't installed yet.\n"
        "\n"
        "Install them with:\n"
        "  pip install 'nemo-platform[all]'\n",
        err=True,
    )
    raise typer.Exit(1)


def _parse_csv_option(value: str | None) -> list[str] | None:
    """Parse a comma-separated CLI option into a list."""
    if value is None:
        return None
    if value == "":
        return []
    return [item for item in value.split(",") if item]


def _wait_for_healthy(
    host: str,
    port: int,
    timeout: int = _HEALTH_TIMEOUT_SECONDS,
    poll_interval: float = _HEALTH_POLL_INTERVAL,
) -> bool:
    """Poll the platform health endpoint until it responds or timeout."""
    effective_host = "localhost" if host in ("0.0.0.0", "::") else host  # noqa: S104
    url = str(httpx.URL(scheme="http", host=effective_host, port=port, path="/health/ready"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(poll_interval)
    return False


def _warn_bind_all(host: str) -> None:
    if host in ("0.0.0.0", "::"):  # noqa: S104
        typer.echo(
            f"Warning: binding to {host} makes the service reachable on all network interfaces.",
            err=True,
        )


def _effective_base_dir() -> str | None:
    """Allow test/internal override of the base state dir via env var."""
    return os.environ.get("_NMP_STATE_DIR")


def _find_sole_running_scope(base_dir: Path | None) -> str:
    """Find the scope of the single running instance for this working directory.

    When the user runs ``restart`` without ``--instance`` or ``--port``, we
    can't know which scope to target because the scope includes the port.
    This function scans all running instances whose scope starts with the
    same git-root hash prefix.  If exactly one matches, return it.
    Otherwise fall back to the default scope (hash-DEFAULT_PORT).
    """
    prefix = compute_scope(port=0, instance_name=None).rsplit("-", 1)[0]
    running = [i for i in list_instances(base_dir=base_dir) if i.alive and i.scope.startswith(prefix + "-")]
    if len(running) == 1:
        return running[0].scope
    return compute_scope(port=_DEFAULT_PORT)


def _fail_already_running(scope: str, base_dir: Path | None) -> NoReturn:
    """Print 'already running' error and raise ``typer.Exit(1)``."""
    desc = read_descriptor(scope, base_dir=base_dir)
    pid_info = f" (pid {desc.pid})" if desc else ""
    typer.echo(
        f"Instance '{scope}' is already running{pid_info}.\n"
        "Stop it first with: nemo services stop\n"
        "Or restart with:    nemo services restart",
        err=True,
    )
    raise typer.Exit(1)


def _fail_port_conflict(conflict: PortConflict) -> NoReturn:
    """Print port conflict error on stderr and raise ``typer.Exit(1)``."""
    lines = format_port_conflict(conflict)
    typer.echo(lines[0], err=True)
    for line in lines[1:]:
        typer.echo(f"  {line}", err=True)
    raise typer.Exit(1)


def _ensure_port_available(host: str, port: int, scope: str, *, base_dir: Path | None) -> None:
    conflict = check_port_available_for_start(host, port, scope, base_dir=base_dir)
    if conflict is not None:
        _fail_port_conflict(conflict)


# ---------------------------------------------------------------------------
# run (foreground)
# ---------------------------------------------------------------------------


@services_app.command("run")
def run_services(
    services: Annotated[
        str | None,
        typer.Option(
            "--services",
            help="Comma-separated services to run, e.g. models,entities,jobs. Defaults to all available services.",
        ),
    ] = None,
    service_group: Annotated[
        str | None,
        typer.Option(
            "--service-group",
            help="Run a predefined service group. Cannot be combined with --services.",
        ),
    ] = None,
    controllers: Annotated[
        str | None,
        typer.Option(
            "--controllers",
            help="Comma-separated controllers to run, e.g. jobs,models.",
        ),
    ] = None,
    controller_group: Annotated[
        str | None,
        typer.Option(
            "--controller-group",
            help="Run a predefined controller group. Cannot be combined with --controllers.",
        ),
    ] = None,
    sidecars: Annotated[
        str | None,
        typer.Option(
            "--sidecars",
            help="Comma-separated sidecars to run, e.g. adapters,cache.",
        ),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", help="Path to a platform configuration YAML file."),
    ] = None,
    host: Annotated[str, typer.Option("--host", help="Host to bind to.")] = _DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Port to bind to.")] = _DEFAULT_PORT,
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance", help="Instance name. Defaults to a name derived from the working directory and port."
        ),
    ] = None,
) -> None:
    """Run platform services in the foreground.  Ctrl-C to stop."""
    _require_services_extra()
    _warn_bind_all(host)

    scope = compute_scope(port=port, instance_name=instance)
    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    _ensure_port_available(host, port, scope, base_dir=base_dir)

    try:
        lock_fd = acquire_lock(scope, base_dir=base_dir)
    except InstanceAlreadyRunningError:
        _fail_already_running(scope, base_dir)

    # _NMP_LAUNCH_MODE is set by start_background() when this process was
    # spawned via ``nemo services start``.  Without it we default to
    # "foreground", which protects interactive ``run`` sessions from being
    # killed by ``stop``.
    mode = "background" if os.environ.get("_NMP_LAUNCH_MODE") == "background" else "foreground"

    desc = InstanceDescriptor(
        pid=os.getpid(),
        scope=scope,
        host=host,
        port=port,
        mode=mode,
        create_time=get_create_time(os.getpid()),
        services=_parse_csv_option(services),
        controllers=_parse_csv_option(controllers),
        service_group=service_group,
        controller_group=controller_group,
        sidecars=_parse_csv_option(sidecars),
        config_path=config,
    )
    write_descriptor(desc, base_dir=base_dir)

    def _cleanup() -> None:
        remove_descriptor(scope, base_dir=base_dir)
        try:
            os.close(lock_fd)
        except OSError:
            pass

    from nmp.platform_runner.run import run_platform

    run_platform(
        services=_parse_csv_option(services),
        service_group=service_group,
        controllers=_parse_csv_option(controllers),
        controller_group=controller_group,
        sidecars=_parse_csv_option(sidecars),
        config_path=config,
        host=host,
        port=port,
        on_shutdown=_cleanup,
    )


# ---------------------------------------------------------------------------
# start (background)
# ---------------------------------------------------------------------------


@services_app.command("start")
def start_services(
    services: Annotated[
        str | None,
        typer.Option(
            "--services",
            help="Comma-separated services to run, e.g. models,entities,jobs.",
        ),
    ] = None,
    service_group: Annotated[
        str | None,
        typer.Option(
            "--service-group",
            help="Run a predefined service group. Cannot be combined with --services.",
        ),
    ] = None,
    controllers: Annotated[
        str | None,
        typer.Option(
            "--controllers",
            help="Comma-separated controllers to run, e.g. jobs,models.",
        ),
    ] = None,
    controller_group: Annotated[
        str | None,
        typer.Option(
            "--controller-group",
            help="Run a predefined controller group. Cannot be combined with --controllers.",
        ),
    ] = None,
    sidecars: Annotated[
        str | None,
        typer.Option(
            "--sidecars",
            help="Comma-separated sidecars to run, e.g. adapters,cache.",
        ),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", help="Path to a platform configuration YAML file."),
    ] = None,
    host: Annotated[str, typer.Option("--host", help="Host to bind to.")] = _DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", help="Port to bind to.")] = _DEFAULT_PORT,
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance", help="Instance name. Defaults to a name derived from the working directory and port."
        ),
    ] = None,
) -> None:
    """Start platform services in the background.

    Detaches the process, polls /health/ready, then returns.

    Examples:
      nemo services start
      nemo services start --services entities,models --port 9090
    """
    _require_services_extra()
    if services is not None and service_group is not None:
        raise typer.BadParameter("Cannot combine --services with --service-group.")
    if controllers is not None and controller_group is not None:
        raise typer.BadParameter("Cannot combine --controllers with --controller-group.")
    _warn_bind_all(host)

    scope = compute_scope(port=port, instance_name=instance)
    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    if is_instance_alive(scope, base_dir=base_dir):
        _fail_already_running(scope, base_dir)

    _ensure_port_available(host, port, scope, base_dir=base_dir)

    typer.echo("Starting platform services...")
    proc = start_background(
        scope=scope,
        services=_parse_csv_option(services),
        service_group=service_group,
        controllers=_parse_csv_option(controllers),
        controller_group=controller_group,
        sidecars=_parse_csv_option(sidecars),
        config_path=config,
        host=host,
        port=port,
        base_dir=base_dir,
    )

    if not _wait_for_healthy(host, port):
        exit_code = proc.poll()
        if exit_code is not None:
            typer.echo(f"Service process exited early (exit code {exit_code})", err=True)
        else:
            typer.echo(
                f"Platform did not become ready within {_HEALTH_TIMEOUT_SECONDS}s",
                err=True,
            )
        log = log_path_for(scope, base_dir=base_dir)
        typer.echo(f"Check {log} for details.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Platform services started (pid {proc.pid}, scope {scope})")


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


@services_app.command("stop")
def stop_services_cmd(
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait before SIGKILL."),
    ] = _DEFAULT_STOP_TIMEOUT,
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance", help="Instance name. Defaults to a name derived from the working directory and port."
        ),
    ] = None,
    port: Annotated[
        int,
        typer.Option("--port", help="Port (used for scope computation if --instance not given)."),
    ] = _DEFAULT_PORT,
    force: Annotated[
        bool,
        typer.Option("--force", help="Stop even if the instance is running in the foreground."),
    ] = False,
) -> None:
    """Stop running platform services.

    Sends SIGTERM to the running service process and waits for it to exit.
    Falls back to SIGKILL after a timeout.  Foreground instances (started
    with ``run``) are protected; use ``--force`` to override.

    Examples:
      nemo services stop
      nemo services stop --timeout 60
    """
    scope = compute_scope(port=port, instance_name=instance)
    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    try:
        result = stop_instance(scope, base_dir=base_dir, timeout=timeout, force=force)
    except ForegroundInstanceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    if not result.stopped_pids:
        typer.echo("Platform services are not running.")
        return
    pids_str = ", ".join(str(p) for p in result.stopped_pids)
    msg = f"Stopped platform services (pid {pids_str})"
    if result.swept_children:
        n = len(result.swept_children)
        noun = "process" if n == 1 else "processes"
        msg += f" and {n} child {noun}"
    typer.echo(msg)


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


@services_app.command("restart")
def restart_services(
    services: Annotated[
        str | None,
        typer.Option(
            "--services",
            help="Comma-separated services to run. Overrides previous service set.",
        ),
    ] = None,
    service_group: Annotated[
        str | None,
        typer.Option(
            "--service-group",
            help="Run a predefined service group. Overrides previous setting.",
        ),
    ] = None,
    controllers: Annotated[
        str | None,
        typer.Option(
            "--controllers",
            help="Comma-separated controllers to run. Overrides previous controller set.",
        ),
    ] = None,
    controller_group: Annotated[
        str | None,
        typer.Option(
            "--controller-group",
            help="Run a predefined controller group. Overrides previous setting.",
        ),
    ] = None,
    sidecars: Annotated[
        str | None,
        typer.Option(
            "--sidecars",
            help="Comma-separated sidecars to run. Overrides previous setting.",
        ),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", help="Path to a platform configuration YAML file."),
    ] = None,
    host: Annotated[
        str | None,
        typer.Option("--host", help="Host to bind to. Defaults to previous value or 127.0.0.1."),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", help="Port to bind to. Defaults to previous value or 8080."),
    ] = None,
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance", help="Instance name. Defaults to a name derived from the working directory and port."
        ),
    ] = None,
) -> None:
    """Restart platform services.

    Stops any running services and relaunches them.  Without flags, preserves
    the service set from the previous run.  Errors if no previously tracked
    instance exists for the computed scope; does not start a fresh instance.

    Examples:
      nemo services restart
      nemo services restart --services entities,models,agents
    """
    _require_services_extra()
    if services is not None and service_group is not None:
        raise typer.BadParameter("Cannot combine --services with --service-group.")
    if controllers is not None and controller_group is not None:
        raise typer.BadParameter("Cannot combine --controllers with --controller-group.")

    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    if instance is not None or port is not None:
        effective_port = port if port is not None else _DEFAULT_PORT
        scope = compute_scope(port=effective_port, instance_name=instance)
    else:
        scope = _find_sole_running_scope(base_dir)

    prev = read_descriptor(scope, base_dir=base_dir)
    if not is_instance_alive(scope, base_dir=base_dir) and prev is None:
        typer.echo(
            f"No instance found for scope '{scope}'.\nUse `nemo services start` to launch a new instance.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo("Stopping platform services...")
    # restart always produces a background instance, so force=True is
    # appropriate even for foreground targets.
    stop_instance(scope, base_dir=base_dir, force=True)

    effective_services = _parse_csv_option(services) if services is not None else (prev.services if prev else None)
    effective_service_group = service_group if service_group is not None else (prev.service_group if prev else None)
    effective_controllers = (
        _parse_csv_option(controllers) if controllers is not None else (prev.controllers if prev else None)
    )
    effective_controller_group = (
        controller_group if controller_group is not None else (prev.controller_group if prev else None)
    )
    effective_sidecars = _parse_csv_option(sidecars) if sidecars is not None else (prev.sidecars if prev else None)
    effective_config = config if config is not None else (prev.config_path if prev else None)
    effective_host = host if host is not None else (prev.host if prev else _DEFAULT_HOST)
    effective_port = port if port is not None else (prev.port if prev else _DEFAULT_PORT)

    _warn_bind_all(effective_host)

    _ensure_port_available(effective_host, effective_port, scope, base_dir=base_dir)

    typer.echo("Starting platform services...")
    proc = start_background(
        scope=scope,
        services=effective_services,
        service_group=effective_service_group,
        controllers=effective_controllers,
        controller_group=effective_controller_group,
        sidecars=effective_sidecars,
        config_path=effective_config,
        host=effective_host,
        port=effective_port,
        base_dir=base_dir,
    )

    if not _wait_for_healthy(effective_host, effective_port):
        exit_code = proc.poll()
        if exit_code is not None:
            typer.echo(f"Service process exited early (exit code {exit_code})", err=True)
        else:
            typer.echo(
                f"Platform did not become ready within {_HEALTH_TIMEOUT_SECONDS}s",
                err=True,
            )
        log = log_path_for(scope, base_dir=base_dir)
        typer.echo(f"Check {log} for details.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Platform services restarted (pid {proc.pid})")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@services_app.command("status")
def status_services(
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance", help="Instance name. Defaults to a name derived from the working directory and port."
        ),
    ] = None,
    port: Annotated[
        int,
        typer.Option("--port", help="Port (used for scope computation if --instance not given)."),
    ] = _DEFAULT_PORT,
) -> None:
    """Show status of the platform services instance for this scope."""
    scope = compute_scope(port=port, instance_name=instance)
    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    alive = is_instance_alive(scope, base_dir=base_dir)
    desc = read_descriptor(scope, base_dir=base_dir)

    if not alive:
        if desc:
            remove_descriptor(scope, base_dir=base_dir)
        typer.echo(f"No running instance for scope '{scope}'.")
        return

    if desc is None:
        typer.echo(f"Instance '{scope}' has a held lock but no descriptor.")
        return

    uptime = ""
    if desc.started_at:
        try:
            started = datetime.fromisoformat(desc.started_at)
            delta = datetime.now(timezone.utc) - started
            minutes, seconds = divmod(int(delta.total_seconds()), 60)
            hours, minutes = divmod(minutes, 60)
            uptime = f"{hours}h{minutes:02d}m{seconds:02d}s"
        except ValueError:
            uptime = "unknown"

    healthy = _wait_for_healthy(desc.host, desc.port, timeout=3, poll_interval=0.5)
    health_str = "healthy" if healthy else "unhealthy"

    typer.echo(f"Scope:    {desc.scope}")
    typer.echo(f"PID:      {desc.pid}")
    typer.echo(f"Mode:     {desc.mode}")
    typer.echo(f"Address:  {desc.host}:{desc.port}")
    typer.echo(f"Uptime:   {uptime}")
    typer.echo(f"Health:   {health_str}")
    log = log_path_for(scope, base_dir=base_dir)
    if log.exists():
        typer.echo(f"Log:      {log}")


# ---------------------------------------------------------------------------
# ls (list instances)
# ---------------------------------------------------------------------------


@services_app.command("ls")
def ls_services() -> None:
    """List all known service instances on this host."""
    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    instances = list_instances(base_dir=base_dir)
    if not instances:
        typer.echo("No instances found.")
        return

    typer.echo(f"{'SCOPE':<25} {'STATUS':<10} {'PID':<10} {'ADDRESS':<25} {'MODE':<12}")
    for info in instances:
        status = "running" if info.alive else "stopped"
        pid = str(info.descriptor.pid) if info.descriptor else "-"
        addr = f"{info.descriptor.host}:{info.descriptor.port}" if info.descriptor else "-"
        mode = info.descriptor.mode if info.descriptor else "-"
        typer.echo(f"{info.scope:<25} {status:<10} {pid:<10} {addr:<25} {mode:<12}")


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@services_app.command("logs")
def logs_services(
    path_only: Annotated[
        bool,
        typer.Option("--path", help="Print the log file path instead of tailing."),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("-n", "--lines", min=1, help="Number of lines to show from end of log."),
    ] = 50,
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance", help="Instance name. Defaults to a name derived from the working directory and port."
        ),
    ] = None,
    port: Annotated[
        int,
        typer.Option("--port", help="Port (used for scope computation if --instance not given)."),
    ] = _DEFAULT_PORT,
) -> None:
    """Show or locate the service log file.

    Examples:
      nemo services logs
      nemo services logs --path
      nemo services logs -n 100
    """
    scope = compute_scope(port=port, instance_name=instance)
    base_dir_str = _effective_base_dir()
    base_dir = Path(base_dir_str) if base_dir_str else None

    log = log_path_for(scope, base_dir=base_dir)
    if path_only:
        typer.echo(str(log))
        return
    if not log.exists():
        typer.echo(f"No log file found at {log}")
        return
    from collections import deque

    with open(log) as f:
        tail = deque(f, maxlen=lines)
    for line in tail:
        typer.echo(line, nl=False)
