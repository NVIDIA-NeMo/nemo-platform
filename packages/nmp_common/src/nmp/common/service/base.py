# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base service class for NeMo Platform services."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import ClassVar, Dict, Generic, List, Optional, Self, Type, TypeVar, cast, get_args, get_origin

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi
from nemo_platform import AsyncNeMoPlatform, DefaultAsyncHttpxClient
from nmp.common.api.utils import register_query_param_schemas
from nmp.common.config import Configuration, PlatformConfig, ServiceConfig
from nmp.common.controller import Controller
from nmp.common.entities.client import EntityClient

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Configuration for a router including its OpenAPI tag metadata."""

    router: APIRouter
    tag: str
    description: str
    prefix: str = ""


TConfig = TypeVar("TConfig", bound=ServiceConfig)


def _get_config_class_from_generic(cls: type) -> Type[ServiceConfig] | None:
    """Extract the config class from Service[TConfig] generic parameter.

    Args:
        cls: The class to inspect (typically a Service subclass)

    Returns:
        The config class if found, None otherwise
    """
    for base in getattr(cls, "__orig_bases__", ()):
        origin = get_origin(base)
        if origin is not None and issubclass(origin, Service):
            args = get_args(base)
            if args and isinstance(args[0], type) and issubclass(args[0], ServiceConfig):
                return args[0]
    return None


class DependencyProvider:
    """
    Manages SDK, entity client, HTTP client, and config lifecycle for NeMo Platform services.

    Provides lazy initialization, FastAPI dependency wiring, and cleanup.

    The `_http_client` field supports test injection - when set, it's passed to
    `get_async_platform_sdk()` to route requests through ASGI transport in tests.
    See architecture/docs/http-client-injection.md for details.
    """

    def __init__(self) -> None:
        self._http_client: Optional[httpx.AsyncClient] = None
        self._sdk_client: Optional[AsyncNeMoPlatform] = None
        self._platform_config: Optional[PlatformConfig] = None
        self._service_name: str = "platform"

    def get_http_client(self) -> httpx.AsyncClient:
        """Return the httpx.AsyncClient for this provider, creating it lazily.

        Each DependencyProvider manages its own HTTP client by default.
        If you need to share a client across providers (e.g., for connection
        pooling), you can inject the same client via _http_client.
        """
        if self._http_client is None:
            self._http_client = DefaultAsyncHttpxClient()
        return self._http_client

    def get_sdk_client(self, as_service: str | None = None) -> AsyncNeMoPlatform:
        """Return the async platform SDK client.

        Args:
            as_service: If provided, creates a NEW SDK instance with service principal
                       credentials (not cached). Use this for startup code, background
                       tasks, and controllers that run without user request context.
                       The EntityClient dynamically adds auth headers per-request,
                       so for normal request handling the cached instance works fine.

        Returns:
            SDK client - cached instance if as_service is None, new instance otherwise.
        """
        from nmp.common.sdk_factory import get_async_platform_sdk

        # When as_service is specified, return a fresh SDK with service credentials.
        # This is needed for startup/background code where no user auth context exists.
        if as_service is not None:
            return get_async_platform_sdk(as_service=as_service, internal=True, http_client=self._http_client)

        # For request handling, use cached SDK. EntityClient adds auth headers per-request.
        if self._sdk_client is None:
            self._sdk_client = get_async_platform_sdk(http_client=self._http_client)
        return self._sdk_client

    def get_entity_client(self, as_service: str | None = None) -> Optional[EntityClient]:
        """Return the EntityClient.

        Args:
            as_service: If provided, creates a NEW EntityClient backed by an SDK with
                       service principal credentials (not cached). Use this for startup
                       code, background tasks, and controllers that run without user
                       request context.

        Returns:
            EntityClient - new instance with service principal + on-behalf-of SDK
            for request handling, or new instance with explicit service credentials
            if as_service is provided.
        """
        from nemo_platform.resources.entities import AsyncEntitiesResource
        from nmp.common.entities.client import EntityClient

        # When as_service is specified, return a fresh EntityClient with service credentials.
        if as_service is not None:
            sdk = self.get_sdk_client(as_service=as_service)
            entities_api = AsyncEntitiesResource(sdk)
            return EntityClient(entities_api)

        # For request handling, authenticate as the service principal with
        # X-NMP-Principal-On-Behalf-Of set to the current user. This ensures
        # the entity store authorizes the request via service principal bypass
        # while preserving the user's identity for audit/attribution.
        sdk = self._get_entity_sdk_on_behalf_of()
        entities_api = AsyncEntitiesResource(sdk)
        return EntityClient(entities_api)

    def _get_entity_sdk_on_behalf_of(self) -> AsyncNeMoPlatform:
        """Create a per-request SDK for entity operations using service principal + on-behalf-of.

        Uses the cached base SDK and applies per-request headers via .with_options()
        (lightweight — reuses the HTTP connection pool).
        """
        from nmp.common.sdk_factory import with_options_preserving_request_router
        from nmp.common.service.headers import build_downstream_service_headers

        base_sdk = self.get_sdk_client()
        headers = build_downstream_service_headers(self._service_name)

        return with_options_preserving_request_router(base_sdk, set_default_headers=headers)

    def get_platform_config(self) -> PlatformConfig:
        """Return the PlatformConfig (lazily initialized)."""
        if self._platform_config is None:
            self._platform_config = Configuration.get_platform_config()
        return self._platform_config

    def get_request_scoped_sdk(self) -> AsyncNeMoPlatform:
        """Return a request-scoped SDK with current auth and OTEL headers.

        This wraps the cached base SDK with per-request headers via .with_options().
        Used as the FastAPI dependency override for get_sdk_client.
        """
        from nmp.common.sdk_factory import get_request_scoped_sdk

        base_sdk = self.get_sdk_client()  # Cached base SDK
        return get_request_scoped_sdk(base_sdk)

    def setup_dependencies(self, app: FastAPI, service: "Service") -> None:
        """Configure FastAPI dependency overrides."""
        from nmp.common.service.dependencies import (
            get_entity_client,
            get_platform_config,
            get_sdk_client,
            get_service_config,
        )

        app.dependency_overrides[get_sdk_client] = self.get_request_scoped_sdk
        app.dependency_overrides[get_entity_client] = self.get_entity_client
        app.dependency_overrides[get_platform_config] = self.get_platform_config
        if service._service_config is not None:
            app.dependency_overrides[get_service_config] = lambda: service._service_config

    async def close(self) -> None:
        """Close managed clients.

        Each DependencyProvider owns its HTTP client and SDK, so closing them
        here is safe. Called by Service.on_shutdown() during lifespan cleanup.
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
        if self._sdk_client is not None:
            await self._sdk_client.close()
            self._sdk_client = None


class Service(ABC, Generic[TConfig]):
    """
    Base class for all NeMo Platform services.

    Subclasses must implement:
    - get_routers(): List of RouterConfig instances

    Subclasses may override:
    - dependencies: Service names this service depends on (startup waits for them).
    - title: Defaults to "{name} Service" (e.g., "Jobs Service")
    - description: Defaults to "{title} for NeMo Platform"
    - version: Defaults to "0.0.1"
    - on_startup(): Custom initialization (e.g., database setup)
    - on_shutdown(): Custom cleanup (e.g., close connections)
    - startup(): Background startup task

    Example:
        >>> class JobsService(Service[JobsConfig]):
        ...     dependencies = ["entities", "auth", "secrets", "files"]
        ...     def __init__(self):
        ...         super().__init__(name="jobs", module_name="nmp.jobs")
        ...
        ...     def get_routers(self) -> List[RouterConfig]:
        ...         return [
        ...             RouterConfig(jobs.router, tag="Jobs", description="Job operations"),
        ...         ]
    """

    # Class-level dependency list; subclasses override to declare service dependencies.
    dependencies: ClassVar[List[str]] = []

    _service_config: TConfig | None

    def __init__(
        self,
        name: str,
        module_name: str,
        dependency_provider: Optional[DependencyProvider] = None,
        dependencies: Optional[list[str]] = None,
    ):
        """
        Initialize the service.

        Args:
            name: Service name (e.g., "workspaces", "datasets")
            module_name: Full module path (e.g., "nmp.workspaces")
            dependency_provider: Optional dependency provider for SDK, entity client, and config.
                                 If not provided, a default DependencyProvider is created.
            dependencies: Optional list of service names this service depends on. When not
                           provided, the class attribute ``dependencies`` is used. startup()
                           waits for each dependency to be ready before continuing.
        """
        self.name = name
        self.module_name = module_name
        self._app: Optional[FastAPI] = None
        self._startup_background_tasks: list[asyncio.Task] = []
        self._dependency_provider = dependency_provider if dependency_provider is not None else DependencyProvider()
        if dependencies is not None:
            self._dependencies = list(dependencies)
        else:
            self._dependencies = list(getattr(type(self), "dependencies", []))

        # Extract config class from generic type parameter and load config
        config_class = _get_config_class_from_generic(type(self))
        self._service_config = (
            cast(TConfig | None, Configuration.get_service_config(config_class)) if config_class else None
        )

    @property
    def dependency_provider(self) -> DependencyProvider:
        """Access the service's dependency provider."""
        return self._dependency_provider

    def with_config(self, config: TConfig) -> Self:
        """Inject a service config, returning self for chaining.

        Useful for testing where you want to override the auto-loaded config.

        Args:
            config: The service config to inject

        Returns:
            Self for method chaining
        """
        self._service_config = config
        return self

    def create_startup_task(self, coro) -> asyncio.Task:
        """Create a startup background task and track it for testing.

        Use this instead of asyncio.create_task() for tasks that should be
        awaited in tests. TestClient can await these via await_startup_tasks().
        """
        task = asyncio.create_task(coro)
        self._startup_background_tasks.append(task)
        return task

    async def await_startup_tasks(self, timeout: float = 30.0) -> None:
        """Await all pending startup background tasks.

        Called by test fixtures to ensure startup tasks complete before tests run.
        """
        if self._startup_background_tasks:
            await asyncio.wait(self._startup_background_tasks, timeout=timeout)

    # =========================================================================
    # Abstract methods - MUST be implemented by subclasses
    # =========================================================================

    @abstractmethod
    def get_routers(self) -> List[RouterConfig]:
        """
        Return list of router configurations for the service.

        Each RouterConfig includes the router and its OpenAPI tag metadata.

        Returns:
            List of RouterConfig instances
        """
        pass

    # =========================================================================
    # Properties with defaults - MAY be overridden
    # =========================================================================

    @property
    def title(self) -> str:
        """
        Service title for OpenAPI docs.

        Defaults to "{name} Service" with proper title casing.
        E.g., "jobs" -> "Jobs Service", "entity-store" -> "Entity Store Service"
        """
        return f"{self.name.replace('-', ' ').title()} Service"

    @property
    def description(self) -> str:
        """Service description for OpenAPI docs."""
        return f"{self.title} for NeMo Platform"

    @property
    def version(self) -> str:
        """Service version for OpenAPI docs."""
        return "0.0.1"

    @property
    def platform_config(self) -> PlatformConfig:
        """Platform configuration (shared across all services)."""
        return self._dependency_provider.get_platform_config()

    @property
    def service_config(self) -> TConfig | None:
        """Service-specific configuration (typed based on Service[TConfig])."""
        return self._service_config

    # =========================================================================
    # Lifecycle hooks - MAY be overridden for custom behavior
    # =========================================================================

    async def on_startup(self) -> None:
        """
        Called during lifespan startup, before the HTTP server accepts connections.

        Override this to add custom initialization (e.g., database setup).
        When the platform does not run startup() tasks, readiness is still derived
        from is_ready(); return True from is_ready() when initialization is done.

        Example:
            async def on_startup(self) -> None:
                self.db = get_db(self.platform_config.db_url)
                await init_db(self.db, create_all=True)
        """
        pass

    async def on_shutdown(self) -> None:
        """
        Called during lifespan shutdown, after the startup task is cancelled.

        Override this to cleanup resources like database connections.
        If overriding, call super().on_shutdown() to ensure proper cleanup.

        Example:
            async def on_shutdown(self) -> None:
                # Your cleanup code here
                await super().on_shutdown()
        """
        await self._dependency_provider.close()

    def get_controllers(self) -> List["Controller"]:
        """Return list of controllers for the service.

        Override this method to provide background controllers that should
        run alongside the service. Each controller will be wrapped in a Loop
        and registered with the ControllerManager.

        Returns:
            List of Controller instances (default: empty list)
        """
        return []

    def _setup_dependencies(self, app: FastAPI) -> None:
        """Configure FastAPI dependency overrides for the service."""
        self._dependency_provider.setup_dependencies(app, self)

    # =========================================================================
    # Core implementation - NOT intended to be overridden
    # =========================================================================

    def create_app(self) -> FastAPI:
        """
        Create and return the FastAPI application for this service.

        This is a concrete implementation that uses the abstract methods
        and properties to configure the app. Services should NOT override
        this method - instead, override the individual properties and hooks.
        """

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Lifespan context manager for the FastAPI app."""
            logger.info("Starting service...", extra={"service": self.name})

            # Run service-specific startup initialization (e.g., database setup)
            await self.on_startup()

            # Run startup (seeding, config population, etc.) in background.
            startup_task = self.create_startup_task(self.startup())

            yield

            if not startup_task.done():
                startup_task.cancel()
                try:
                    await startup_task
                except asyncio.CancelledError:
                    pass

            # Run service-specific shutdown cleanup
            logger.info("Shutting down service...", extra={"service": self.name})
            await self.on_shutdown()
            logger.info("Service shutdown complete", extra={"service": self.name})

        # Build openapi_tags from RouterConfigs
        router_configs = self.get_routers()
        openapi_tags: List[Dict[str, str]] = [{"name": rc.tag, "description": rc.description} for rc in router_configs]

        app = FastAPI(
            title=self.title,
            description=self.description,
            version=self.version,
            openapi_tags=openapi_tags,
            lifespan=lifespan,
        )

        # Store reference to app for use in on_startup
        self._app = app

        # Store service instance for access by endpoints
        app.state.service = self

        # Setup dependency overrides (e.g., entity client factory)
        self._setup_dependencies(app)

        # Register SDK exception handlers so that HTTP errors from internal
        # service-to-service calls are converted back to HTTP responses
        # (e.g., 400 from entity store -> 400 response, not 500 crash)
        from nmp.common.errors.sdk_exception_handlers import register_sdk_exception_handlers

        register_sdk_exception_handlers(app)

        # Include service-specific routers, tagging any routes that have no tags yet
        for rc in router_configs:
            for route in rc.router.routes:
                if hasattr(route, "tags") and not route.tags:
                    route.tags = [rc.tag]
            app.include_router(rc.router, prefix=rc.prefix)

        # Setup custom OpenAPI schema
        self._setup_custom_openapi(app, openapi_tags)

        return app

    def _setup_custom_openapi(self, app: FastAPI, openapi_tags: List[Dict[str, str]]) -> None:
        """Configure custom OpenAPI schema generation."""

        def custom_openapi():
            if app.openapi_schema:
                return app.openapi_schema
            openapi_schema = get_openapi(
                title=self.title,
                version=self.version,
                summary=f"This is the OpenAPI Schema for the {self.title}.",
                description="",
                routes=app.routes,
                tags=openapi_tags,
            )
            openapi_schema = register_query_param_schemas(openapi_schema)
            app.openapi_schema = openapi_schema
            return app.openapi_schema

        app.openapi = custom_openapi  # type: ignore[method-assign]

    # =========================================================================
    # Startup and readiness
    # =========================================================================

    async def is_ready(self) -> bool:
        """Check if the service is currently ready to serve traffic.

        Invoked by the platform /health/ready and /status handlers. Default implementation returns True.
        Override in subclasses when the service has dependencies (e.g. database) that can degrade; return False when the service cannot serve traffic.
        """
        return True

    async def wait_for_service_ready(
        self,
        service_name: str,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait for another service to be ready before continuing startup.

        This is useful in startup() methods when this service depends on another
        service being ready before it can complete its initialization.

        Automatically uses the platform base_url and http_client from the
        dependency provider.

        Args:
            service_name: Name of the service to wait for (e.g., "entities").
            timeout: Maximum time to wait in seconds.
            poll_interval: Time between polling attempts in seconds.

        Returns:
            True if the service became ready, False if timeout.

        Example:
            async def startup(self) -> None:
                if not await self.wait_for_service_ready("entities"):
                    return  # is_ready() returns False

                # Continue with startup...
        """
        import time

        from nmp.common.observability import MARK_INTERNAL_REQUEST_HEADERS

        status_url = f"{self.platform_config.get_service_url(service_name).rstrip('/')}/status"
        client = self._dependency_provider.get_http_client()

        logger.debug("Waiting for service to be ready", extra={"service": service_name, "url": status_url})

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            try:
                response = await client.get(status_url, timeout=2.0, headers=MARK_INTERNAL_REQUEST_HEADERS)
                if response.status_code == 200:
                    data = response.json()
                    services = data.get("services") or {}
                    ready = services.get("ready") or []
                    if service_name in ready:
                        logger.debug("Service is ready", extra={"service": service_name})
                        return True
                    # If the service isn't in any list (ready/not_ready), it's not
                    # part of this deployment — skip waiting rather than timing out.
                    not_ready = services.get("not_ready") or []
                    not_ready_names = [
                        n.get("name", n) if isinstance(n, dict) else getattr(n, "name", n) for n in not_ready
                    ]
                    if service_name not in ready and service_name not in not_ready_names:
                        logger.debug(
                            "Dependency not present in platform, skipping wait",
                            extra={"service": service_name},
                        )
                        return True
                    # Service is in not_ready; keep polling
            except httpx.RequestError:
                pass
            await asyncio.sleep(poll_interval)

        logger.warning("Timeout waiting for service to be ready", extra={"service": service_name, "timeout": timeout})
        return False

    async def _wait_for_dependencies(self, timeout: float = 120.0) -> bool:
        """Wait for all services in self._dependencies to be ready.

        Uses wait_for_service_ready() for each dependency in order. Useful at the
        start of startup() so the service only proceeds after its dependencies
        are ready. Dependencies are defined on the service class (or passed to the constructor).

        Args:
            timeout: Maximum time to wait per dependency, in seconds.

        Returns:
            True if all dependencies became ready, False if any timed out.
        """
        for dep in self._dependencies:
            logger.debug("Waiting for dependency to be ready", extra={"service": self.name, "dependency": dep})
            if not await self.wait_for_service_ready(dep, timeout=timeout):
                logger.error("Dependency did not become ready", extra={"service": self.name, "dependency": dep})
                return False
        return True

    async def startup(self) -> None:
        """
        Background startup task after HTTP server is accepting connections.

        Default implementation waits for all dependencies (if any) via
        _wait_for_dependencies(), then returns. Override for custom initialization.
        """
        if self._dependencies and not await self._wait_for_dependencies():
            logger.error(
                "One or more dependencies did not become ready",
                extra={"service": self.name, "dependencies": self._dependencies},
            )

    @property
    def app(self) -> FastAPI:
        """
        Get the FastAPI application (creates if not exists).

        This property lazily creates the application on first access
        and caches it for subsequent calls.

        Returns:
            FastAPI application instance
        """
        if self._app is None:
            self._app = self.create_app()
        return self._app

    def __repr__(self) -> str:
        """Return string representation of the service."""
        return f"<{self.__class__.__name__} name={self.name!r}>"
