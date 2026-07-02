# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic API server helpers for platform services."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from nmp.common.auth import AuthorizationMiddleware
from nmp.common.config import get_auth_config, get_platform_config
from nmp.common.http_clients import close_shared_http_clients
from nmp.common.observability import initialize_obs, setup_fastapi_instrumentations, setup_global_instrumentations
from nmp.common.observability.context import create_app_context_dependency
from nmp.common.pyleak import detect_blocking
from nmp.common.service import Service
from nmp.platform_runner.health import create_platform_health_router, get_platform_resource_attributes
from nmp.platform_runner.loader import load_controller_run_func, load_service, order_services_by_dependencies
from nmp.platform_runner.registry import get_available_controllers, get_available_services, get_openapi_service_names
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

logger = logging.getLogger(__name__)


async def platform_global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback exception handler for uncaught platform errors."""
    extra = {
        "method": request.method,
        "path": request.url.path,
        "exc_type": type(exc).__name__,
    }
    if service := getattr(request.state, "service", None):
        extra["service"] = service
    if workspace := getattr(request.state, "workspace", None):
        extra["workspace"] = workspace

    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra=extra,
    )
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


class ConflictRetryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if response.status_code == 409 and "x-should-retry" not in response.headers:
            response.headers["x-should-retry"] = "false"
        return response


class PyleakMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, threshold: float):
        super().__init__(app)
        self.threshold = threshold

    async def dispatch(self, request: Request, call_next) -> Response:
        async with detect_blocking(threshold=self.threshold):
            return await call_next(request)


def preflight_embedded_auth_policy_wasm(auth_config) -> None:
    """Ensure local embedded auth PDP has a loadable policy.wasm before serving traffic."""
    if not auth_config.enabled or auth_config.policy_decision_point_provider != "embedded":
        return

    try:
        from nmp.core.auth.app.embedded_pdp.policy_wasm import ensure_embedded_policy_wasm
    except ImportError as exc:
        raise RuntimeError(
            "Auth is enabled with the embedded PDP, but the nmp-auth package is not installed. "
            "Install nmp-auth or set auth.policy_decision_point_provider='opa'."
        ) from exc

    ensure_embedded_policy_wasm(auto_build=getattr(auth_config, "embedded_pdp_auto_build_wasm", True))


def create_platform_openapi_app() -> FastAPI:
    """Create the platform app used for aggregate OpenAPI generation."""
    services = []
    available_services = get_available_services()
    for service_name in get_openapi_service_names(available_services):
        service_value = available_services[service_name]
        if isinstance(service_value, Service):
            services.append(service_value)
        else:
            services.append(load_service(service_name, service_value))
    return create_app(order_services_by_dependencies(services))


def create_app(
    services: list[Service] | None = None,
    controller_run_funcs: dict[str, object] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    """Create the FastAPI app from service instances."""
    services = services or []
    controller_run_funcs = controller_run_funcs or {}
    controller_stop_signal = threading.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting Nemo Platform server")
        controller_threads = []
        if controller_run_funcs:
            logger.info("Starting controllers in lifespan: %s", list(controller_run_funcs))
            for name, run_func in controller_run_funcs.items():
                thread = threading.Thread(
                    target=run_func,
                    args=(controller_stop_signal,),
                    name=f"controller-{name}",
                    daemon=True,
                )
                thread.start()
                controller_threads.append(thread)

        platform_config = get_platform_config()
        if platform_config.seed_on_startup:
            try:
                from nmp.platform_seed import run_platform_seed_from_startup

                asyncio.create_task(run_platform_seed_from_startup())
                logger.info("Platform seed task scheduled")
            except ImportError as error:
                logger.warning("platform.seed_on_startup is True but platform_seed is not installed: %s", error)

        app.state.controller_threads = controller_threads
        app.state.controller_stop_signal = controller_stop_signal

        yield

        controller_stop_signal.set()
        for thread in controller_threads:
            thread.join(timeout=5)

        await close_shared_http_clients()
        logger.info("Shutting down Nemo Platform API server")

    app = FastAPI(
        title="Nemo Platform API",
        description="API for Nemo Platform services",
        version="0.0.1",
        lifespan=lifespan,
    )
    app.add_middleware(ConflictRetryMiddleware)

    pyleak_threshold = float(os.environ.get("PYLEAK_THRESHOLD", "0"))
    if pyleak_threshold > 0:
        app.add_middleware(PyleakMiddleware, threshold=pyleak_threshold)

    auth_config = get_auth_config()
    logger.info("Adding AuthorizationMiddleware", extra={"auth_enabled": auth_config.enabled})
    app.add_middleware(AuthorizationMiddleware, service_name="platform", http_client=http_client)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    app.state.service_configs = {}
    app.include_router(create_platform_health_router(services))

    redirect_root_to_studio = get_platform_config().redirect_root_to_studio

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    async def root_handler() -> Response:
        if redirect_root_to_studio:
            return RedirectResponse(url="/studio", status_code=301)
        return Response(status_code=200, content="OK")

    for service_instance in services:
        service_app = service_instance.app
        app.dependency_overrides.update(service_app.dependency_overrides)
        exception_handlers = {
            exc_type: handler
            for exc_type, handler in service_app.exception_handlers.items()
            if exc_type is not Exception
        }
        app.exception_handlers.update(exception_handlers)
        app.include_router(
            router=service_app.router,
            prefix=f"/apis/{service_instance.name}",
            dependencies=[Depends(create_app_context_dependency(service_instance.name))],
        )
        configure_app = getattr(service_instance, "configure_app", None)
        if configure_app is not None and callable(configure_app):
            if "app" in inspect.signature(configure_app).parameters:
                configure_app(app)
        setattr(app.state, f"{service_instance.name.replace('-', '_')}_service", service_instance)
        if service_instance._service_config is not None:
            app.state.service_configs[type(service_instance._service_config)] = service_instance._service_config

    app.add_exception_handler(Exception, platform_global_exception_handler)
    return app


def run_server(services: list[Service] | None = None, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Run the platform API server."""
    preflight_embedded_auth_policy_wasm(get_auth_config())
    app = create_app(services or [])
    setup_fastapi_instrumentations(app)
    uvicorn.run(app, host=host, port=port, log_config=None)


def run_server_with_reload(app_factory: str, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Run the platform API server with uvicorn reload enabled."""
    preflight_embedded_auth_policy_wasm(get_auth_config())
    reload_dirs = [
        "packages/nmp_platform/src",
        "services/core",
        "packages/nmp_common/src",
        "packages/nmp_platform_runner/src",
    ]
    logger.warning("Hot reload is enabled. Controllers will restart with each reload.")
    uvicorn.run(
        app_factory,
        host=host,
        port=port,
        reload=True,
        reload_dirs=reload_dirs,
        log_config=None,
        access_log=False,
        log_level="warning",
        factory=True,
    )


_obs_initialized = False


def create_default_app() -> FastAPI:
    """Factory used by uvicorn reload mode."""
    global _obs_initialized

    if not _obs_initialized:
        initialize_obs(resource_attributes=get_platform_resource_attributes())
        setup_global_instrumentations()
        _obs_initialized = True

    service_names_env = os.environ.get("NMP_SERVICES", "")
    controller_names_env = os.environ.get("NMP_CONTROLLERS", "")

    available_services = get_available_services()
    available_controllers = get_available_controllers()

    service_names = (
        [name for name in service_names_env.split(",") if name] if service_names_env else list(available_services)
    )
    controller_names = (
        [name for name in controller_names_env.split(",") if name]
        if controller_names_env
        else list(available_controllers)
    )

    services = []
    for service_name in service_names:
        service_value = available_services.get(service_name)
        if service_value is None:
            available = ", ".join(sorted(available_services))
            raise ValueError(
                "Unknown service %r requested via NMP_SERVICES=%r. Available services: %s"
                % (service_name, service_names_env, available)
            )
        if isinstance(service_value, Service):
            services.append(service_value)
        else:
            services.append(load_service(service_name, service_value))
    services = order_services_by_dependencies(services)

    controller_run_funcs = {}
    for controller_name in controller_names:
        controller_value = available_controllers.get(controller_name)
        if controller_value is None:
            available = ", ".join(sorted(available_controllers))
            raise ValueError(
                "Unknown controller %r requested via NMP_CONTROLLERS=%r. Available controllers: %s"
                % (controller_name, controller_names_env, available)
            )
        if callable(controller_value):
            controller_run_funcs[controller_name] = controller_value
        else:
            controller_run_funcs[controller_name] = load_controller_run_func(controller_name, controller_value)

    return create_app(services, controller_run_funcs=controller_run_funcs)
