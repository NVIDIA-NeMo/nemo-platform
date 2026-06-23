# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Programmatic platform runner entrypoint."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Mapping

from nmp.common.config import get_auth_config, get_common_service_config, get_service_config
from nmp.common.observability import initialize_obs, setup_global_instrumentations
from nmp.common.observability.otel import settings as otel_settings
from nmp.common.service import CircularDependencyError, Service
from nmp.common.version import platform_api_version
from nmp.platform_runner.config import apply_run_environment, resolve_run_configuration
from nmp.platform_runner.health import get_platform_resource_attributes
from nmp.platform_runner.loader import load_controller_run_func, load_service, order_services_by_dependencies
from nmp.platform_runner.registry import AVAILABLE_SIDECARS
from nmp.platform_runner.server import run_server, run_server_with_reload
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()


def _startup_phase(name: str, t0: float) -> None:
    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    logger.info("[STARTUP] %s: %dms", name, elapsed_ms)


def _database_display(db_url: str) -> str:
    """Format a SQLAlchemy database URL for the startup banner."""
    try:
        from sqlalchemy.engine import make_url

        parsed = make_url(db_url)
    except Exception:
        logger.debug("Failed to parse database URL for startup banner", exc_info=True)
        db_type = db_url.split("://")[0].split("+")[0] if "://" in db_url else "unknown"
        return db_type

    db_type = parsed.drivername.split("+", 1)[0]
    if db_type == "sqlite":
        return f"{db_type} ({parsed.database or ''})"
    return db_type


def run_controllers_in_threads(
    controller_run_funcs: dict[str, Callable],
    stop_signal: threading.Event,
) -> list[threading.Thread]:
    """Start controller run functions in daemon threads."""
    threads = []
    for name, run_func in controller_run_funcs.items():
        thread = threading.Thread(target=run_func, args=(stop_signal,), name=f"controller-{name}", daemon=True)
        thread.start()
        threads.append(thread)
    return threads


def run_platform(
    *,
    services: list[str] | None = None,
    service_group: str | None = None,
    controllers: list[str] | None = None,
    controller_group: str | None = None,
    sidecars: list[str] | None = None,
    config_path: str | None = None,
    host: str = "0.0.0.0",
    port: int = 8080,
    reload_app_factory: str | None = None,
    on_shutdown: Callable[[], object] | None = None,
) -> None:
    """Start the platform API and selected controllers in-process."""
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    resolved = resolve_run_configuration(
        services=services,
        service_group=service_group,
        controllers=controllers,
        controller_group=controller_group,
        sidecars=sidecars,
        config_path=config_path,
        host=host,
        port=port,
    )
    apply_run_environment(resolved)
    _startup_phase("resolve_config", t0)

    service_config = get_common_service_config()
    if otel_settings.log_format != service_config.log_format:
        otel_settings.log_format = service_config.log_format
    if otel_settings.log_level != service_config.log_level:
        otel_settings.log_level = service_config.log_level

    t0 = time.perf_counter()
    initialize_obs(resource_attributes=get_platform_resource_attributes())
    setup_global_instrumentations()
    _startup_phase("observability_init", t0)

    collisions = resolved.controllers & resolved.sidecars
    if collisions:
        raise ValueError(f"Controller/sidecar name collision: {', '.join(sorted(collisions))}")

    service_instances = _load_service_instances(sorted(resolved.services), resolved.available_services)
    controller_run_funcs = _load_run_functions(
        sorted(resolved.controllers), resolved.available_controllers, "controller"
    )
    sidecar_run_funcs = _load_run_functions(sorted(resolved.sidecars), AVAILABLE_SIDECARS, "sidecar")
    _startup_phase("total_to_server", t_total)

    controller_stop_signal = threading.Event()

    def signal_handler(signum: int, _frame: object) -> None:
        logger.info("Received signal %s, initiating shutdown", signum)
        controller_stop_signal.set()
        if on_shutdown is not None:
            try:
                on_shutdown()
            except Exception:
                logger.debug("on_shutdown callback failed", exc_info=True)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    _display_banner(
        services=service_instances,
        controllers=list(controller_run_funcs),
        sidecars=list(sidecar_run_funcs),
        host=resolved.host,
        port=resolved.port,
    )

    controller_threads: list[threading.Thread] = []
    try:
        reload_enabled = os.environ.get("UVICORN_RELOAD", "").lower() in {"true", "1", "yes"}
        if reload_enabled:
            run_server_with_reload(
                reload_app_factory or "nmp.platform_runner.server:create_default_app",
                host=resolved.host,
                port=resolved.port,
            )
        else:
            if controller_run_funcs:
                controller_threads.extend(run_controllers_in_threads(controller_run_funcs, controller_stop_signal))
            if sidecar_run_funcs:
                controller_threads.extend(run_controllers_in_threads(sidecar_run_funcs, controller_stop_signal))
            run_server(service_instances, host=resolved.host, port=resolved.port)
    except ValueError as error:
        logger.error("Configuration error: %s", error)
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as error:
        logger.exception("Fatal error occurred")
        raise SystemExit(1) from error
    finally:
        controller_stop_signal.set()
        if on_shutdown is not None:
            try:
                on_shutdown()
            except Exception:
                logger.debug("on_shutdown callback failed", exc_info=True)
        for thread in controller_threads:
            thread.join(timeout=10)
            if thread.is_alive():
                logger.warning("Controller thread %s did not finish in time", thread.name)


def _load_service_instances(
    service_names: list[str],
    available_services: dict[str, str | Service],
) -> list[Service]:
    service_instances: list[Service] = []
    if not service_names:
        return service_instances

    start_time = time.perf_counter()
    for service_name in service_names:
        service_start = time.perf_counter()
        service_value = available_services[service_name]
        try:
            service_instance = (
                service_value if isinstance(service_value, Service) else load_service(service_name, service_value)
            )
        except (ImportError, TypeError, AttributeError, ValueError) as error:
            logger.error("Failed to load service %s: %s", service_name, error)
            raise SystemExit(1) from error
        service_instances.append(service_instance)
        _startup_phase(f"service:{service_name}", service_start)

    try:
        service_instances = order_services_by_dependencies(service_instances)
    except CircularDependencyError as error:
        logger.error("Cannot start services: circular dependency among services: %s", error)
        raise SystemExit(1) from error

    _startup_phase("all_services_loaded", start_time)
    return service_instances


def _load_run_functions(
    names: list[str],
    registry: Mapping[str, str | Callable],
    kind: str,
) -> dict[str, Callable]:
    run_funcs: dict[str, Callable] = {}
    for name in names:
        t0 = time.perf_counter()
        value = registry[name]
        try:
            if callable(value):
                run_funcs[name] = value
            else:
                run_funcs[name] = load_controller_run_func(name, value)
        except (ImportError, TypeError, AttributeError, ValueError) as error:
            logger.error("Failed to load %s %s: %s", kind, name, error)
            raise SystemExit(1) from error
        _startup_phase(f"{kind}:{name}", t0)
    return run_funcs


def _display_banner(
    *,
    services: list[Service],
    controllers: list[str],
    sidecars: list[str],
    host: str,
    port: int,
) -> None:
    service_names = [service.name for service in services]
    url = f"http://{host}:{port}"
    if otel_settings.log_format != "plain":
        logger.info(
            "Nemo Platform starting",
            extra={
                "version": platform_api_version,
                "url": url,
                "host": host,
                "port": port,
                "services": service_names,
                "controllers": controllers,
                "sidecars": sidecars,
            },
        )
        return

    from nmp.core.entities.config import EntitiesConfig

    entities_config = get_service_config(EntitiesConfig)
    db_url = entities_config.database_config.sqlalchemy_database_url()
    db_display = _database_display(db_url)

    auth_config = get_auth_config()
    auth_status = "enabled" if auth_config.enabled else "disabled"

    banner_text = Text()
    banner_text.append("Nemo Platform\n", style="bold cyan")
    banner_text.append(f"v{platform_api_version}\n\n", style="dim")
    banner_text.append("URL: ", style="bold")
    banner_text.append(f"{url}\n", style=f"green link {url}")
    banner_text.append("Database: ", style="bold")
    banner_text.append(f"{db_display}\n", style="dim")
    banner_text.append("Auth: ", style="bold")
    banner_text.append(f"{auth_status}\n\n", style="dim")
    banner_text.append(f"Services ({len(service_names)}): ", style="bold")
    banner_text.append(", ".join(service_names) if service_names else "none", style="green" if service_names else "dim")
    banner_text.append("\n")
    banner_text.append(f"Controllers ({len(controllers)}): ", style="bold")
    banner_text.append(", ".join(controllers) if controllers else "none", style="green" if controllers else "dim")
    banner_text.append("\n")
    banner_text.append(f"Sidecars ({len(sidecars)}): ", style="bold")
    banner_text.append(", ".join(sidecars) if sidecars else "none", style="green" if sidecars else "dim")
    console.print(Panel(banner_text, border_style="cyan", padding=(0, 1)))
