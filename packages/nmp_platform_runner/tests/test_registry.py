# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter
from nemo_platform_plugin.controller import NemoController
from nemo_platform_plugin.service import NemoService, RouterSpec
from nmp.platform_runner import registry


def clear_registry_caches() -> None:
    registry.get_available_services.cache_clear()
    registry.get_available_controllers.cache_clear()


class AgentsService(NemoService):
    name = "agents"

    def get_routers(self) -> list[RouterSpec]:
        return [RouterSpec(router=APIRouter())]


class AgentsDeploymentController(NemoController):
    name = "agents-deployment"

    async def list_objects(self) -> list:
        return []

    async def reconcile_one(self, _obj: object) -> None:
        return None


def test_service_groups_include_plugin_services(monkeypatch):
    clear_registry_caches()
    monkeypatch.setattr(registry, "discover_services", lambda: {"agents": AgentsService})
    monkeypatch.setattr(
        registry,
        "AVAILABLE_SERVICES",
        {"auth": "nmp.core.auth.main:service", "hello-world": "nmp.hello_world.main:service"},
    )
    monkeypatch.setattr(registry, "CORE_SERVICES", ["auth"])
    monkeypatch.setattr(registry, "API_SERVICES", ["hello-world"])

    available = registry.get_available_services()
    groups = registry.get_service_groups(available)

    assert "agents" not in groups["core"]
    assert "agents" in groups["api"]
    assert "agents" in groups["all"]


def test_controller_groups_include_plugin_controllers(monkeypatch):
    clear_registry_caches()
    monkeypatch.setattr(registry, "discover_controllers", lambda: {"agents-deployment": AgentsDeploymentController})
    monkeypatch.setattr(registry, "AVAILABLE_CONTROLLERS", {"jobs": "nmp.core.jobs.controllers.main:run"})

    available = registry.get_available_controllers()
    groups = registry.get_controller_groups(available)

    assert "agents-deployment" not in groups["core"]
    assert "agents-deployment" in groups["all"]


def test_default_controllers_include_plugin_controllers(monkeypatch):
    clear_registry_caches()
    monkeypatch.setattr(registry, "discover_controllers", lambda: {"agents-deployment": AgentsDeploymentController})
    monkeypatch.setattr(registry, "AVAILABLE_CONTROLLERS", {"jobs": "nmp.core.jobs.controllers.main:run"})

    available = registry.get_available_controllers()
    groups = registry.get_controller_groups(available)

    assert "agents-deployment" in registry.get_default_controllers(groups)


def test_openapi_services_are_explicit_and_do_not_auto_include_plugins(monkeypatch):
    clear_registry_caches()
    monkeypatch.setattr(
        registry,
        "AVAILABLE_SERVICES",
        {
            "auth": "nmp.core.auth.main:service",
            "evaluation": "nmp.evaluator.main:service",
            "hello-world": "nmp.hello_world.main:service",
        },
    )
    monkeypatch.setattr(registry, "OPENAPI_SERVICES", ["auth", "evaluation"])
    monkeypatch.setattr(registry, "discover_services", lambda: {"agents": AgentsService})

    available = registry.get_available_services()

    assert registry.get_openapi_service_names(available) == ["auth", "evaluation"]


def test_intake_is_registered_as_api_and_openapi_service():
    clear_registry_caches()
    available = registry.get_available_services()
    groups = registry.get_service_groups(available)

    assert available["intake"] == "nmp.intake.main:service"
    assert "intake" not in groups["core"]
    assert "intake" in groups["api"]
    assert "intake" in registry.get_openapi_service_names(available)
