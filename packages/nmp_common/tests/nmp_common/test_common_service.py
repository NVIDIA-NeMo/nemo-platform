# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for nmp.common.service module."""

from typing import List

import pytest
from fastapi import APIRouter, FastAPI
from nmp.common.service import DependencyProvider, RouterConfig, Service


def _route_paths(app: FastAPI) -> set[str]:
    """Collect all route paths, compatible with FastAPI 0.138+ _IncludedRouter."""
    paths: set[str] = set()
    queue = list(app.routes)
    while queue:
        route = queue.pop()
        if hasattr(route, "path"):
            paths.add(route.path)
        fn = getattr(route, "effective_candidates", None)
        if callable(fn):
            queue.extend(fn())  # type: ignore[arg-type]
    return paths


class MockService(Service):
    """Mock implementation of Service for testing."""

    def __init__(self):
        super().__init__(name="test-service", module_name="nmp.test")

    def get_routers(self) -> List[RouterConfig]:
        router = APIRouter()

        @router.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        return [RouterConfig(router, tag="Test", description="Test endpoints")]


class TestRouterConfig:
    """Tests for RouterConfig dataclass."""

    def test_router_config_creation(self):
        """Test creating a RouterConfig."""
        router = APIRouter()
        config = RouterConfig(router=router, tag="Test", description="Test description")

        assert config.router is router
        assert config.tag == "Test"
        assert config.description == "Test description"


class TestServiceBase:
    """Tests for Service base class."""

    def test_service_init(self):
        """Test Service initialization."""
        service = MockService()

        assert service.name == "test-service"
        assert service.module_name == "nmp.test"

    def test_service_title(self):
        """Test Service title property."""
        service = MockService()
        assert service.title == "Test Service Service"

    def test_service_description(self):
        """Test Service description property."""
        service = MockService()
        assert "Test Service Service" in service.description

    def test_service_version(self):
        """Test Service version property."""
        service = MockService()
        assert service.version == "0.0.1"

    @pytest.mark.asyncio
    async def test_service_is_ready_default(self):
        """Test is_ready() default returns True."""
        service = MockService()
        assert await service.is_ready() is True

    def test_service_repr(self):
        """Test Service __repr__."""
        service = MockService()
        assert "MockService" in repr(service)
        assert "test-service" in repr(service)

    def test_service_get_routers(self):
        """Test get_routers returns RouterConfig list."""
        service = MockService()
        routers = service.get_routers()

        assert len(routers) == 1
        assert isinstance(routers[0], RouterConfig)
        assert routers[0].tag == "Test"

    def test_service_create_app(self):
        """Test Service creates FastAPI app."""
        service = MockService()
        app = service.create_app()

        assert app is not None
        assert app.title == service.title
        assert app.version == service.version

    def test_service_app_property_caches(self):
        """Test app property returns cached instance."""
        service = MockService()
        app1 = service.app
        app2 = service.app

        assert app1 is app2

    def test_service_custom_router_included(self):
        """Test custom routers are included in app."""
        service = MockService()
        app = service.app

        route_paths = _route_paths(app)
        assert "/test" in route_paths


class TestServiceAsync:
    """Async tests for Service class."""

    @pytest.mark.asyncio
    async def test_service_startup(self):
        """Test startup runs without error; is_ready() remains True."""
        service = MockService()
        assert await service.is_ready() is True

        await service.startup()

        assert await service.is_ready() is True

    @pytest.mark.asyncio
    async def test_service_on_startup_default(self):
        """Test on_startup default implementation does nothing."""
        service = MockService()
        # Should not raise
        await service.on_startup()

    @pytest.mark.asyncio
    async def test_service_on_shutdown_default(self):
        """Test on_shutdown default implementation does nothing."""
        service = MockService()
        # Should not raise
        await service.on_shutdown()

    @pytest.mark.asyncio
    async def test_service_is_ready_default(self):
        """Test is_ready() default returns True."""
        service = MockService()
        assert await service.is_ready() is True


class TestDependencyProvider:
    """Tests for DependencyProvider class."""

    def test_init(self):
        """Test DependencyProvider initialization."""
        provider = DependencyProvider()
        assert provider._sdk_client is None
        assert provider._http_client is None

    @pytest.mark.asyncio
    async def test_close_without_clients(self):
        """Test close when no clients were created."""
        provider = DependencyProvider()
        await provider.close()  # Should not raise


class TestServiceWithProvider:
    """Tests for Service with DependencyProvider."""

    def test_service_has_provider(self):
        """Test Service creates DependencyProvider by default."""
        service = MockService()
        assert service.dependency_provider is not None
        assert isinstance(service.dependency_provider, DependencyProvider)
