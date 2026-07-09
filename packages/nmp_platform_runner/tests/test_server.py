# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import builtins
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.common.config import AuthConfig, Configuration
from nmp.common.config.base import OIDCConfig
from nmp.common.service import Service
from nmp.platform_runner import server
from nmp.platform_runner.health import ReadinessCheck, create_platform_health_router


def _make_auth_config(*, enabled: bool) -> AuthConfig:
    return AuthConfig(
        enabled=enabled,
        policy_decision_point_base_url="http://localhost:8181",
        oidc=OIDCConfig(enabled=False),
    )


class PluginService(Service):
    def __init__(self):
        super().__init__(name="agents", module_name="test.plugin")

    def get_routers(self):
        return []


async def _ready() -> bool:
    return True


async def _not_ready() -> bool:
    return False


def _client_for_health_checks(checks: list[ReadinessCheck]) -> TestClient:
    app = FastAPI()
    app.include_router(create_platform_health_router([PluginService()], readiness_checks=checks))
    return TestClient(app)


def _patch_platform_app_config(monkeypatch, *, seed_on_startup: bool):
    auth_cfg = _make_auth_config(enabled=False)
    platform_cfg = _make_platform_config_mock()
    platform_cfg.seed_on_startup = seed_on_startup
    monkeypatch.setattr(server, "get_platform_config", lambda: platform_cfg)
    monkeypatch.setattr(server, "get_auth_config", lambda: auth_cfg)

    import nmp.common.auth.middleware as auth_middleware

    monkeypatch.setattr(auth_middleware, "get_auth_config", lambda: auth_cfg)
    return platform_cfg


def _wait_for_response(client: TestClient, path: str, status_code: int, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    last_response = None
    while time.monotonic() < deadline:
        last_response = client.get(path)
        if last_response.status_code == status_code:
            return last_response
        time.sleep(0.05)
    return last_response


def test_platform_health_ready_includes_startup_readiness_checks():
    client = _client_for_health_checks(
        [ReadinessCheck(name="platform-seed", is_ready=_not_ready, message=lambda: "pending")]
    )

    response = client.get("/health/ready")
    assert response.status_code == 503

    status = client.get("/status").json()
    assert "agents" in status["services"]["ready"]
    assert {"name": "platform-seed", "message": "pending"} in status["services"]["not_ready"]


def test_platform_health_status_reports_ready_startup_checks():
    client = _client_for_health_checks([ReadinessCheck(name="platform-seed", is_ready=_ready)])

    response = client.get("/health/ready")
    assert response.status_code == 200

    status = client.get("/status").json()
    assert "platform-seed" in status["services"]["ready"]


def test_create_platform_openapi_app_includes_explicit_service_instances(monkeypatch):
    plugin_service = PluginService()
    captured: dict[str, object] = {}

    monkeypatch.setattr(server, "get_available_services", lambda: {"agents": plugin_service, "auth": "skip"})
    monkeypatch.setattr(server, "get_openapi_service_names", lambda _available: ["agents"])
    monkeypatch.setattr(server, "order_services_by_dependencies", lambda services: services)

    def fake_create_app(services, _controller_run_funcs=None, _http_client=None):
        captured["services"] = services
        return FastAPI()

    monkeypatch.setattr(server, "create_app", fake_create_app)

    server.create_platform_openapi_app()

    assert captured["services"] == [plugin_service]


def test_create_default_app_uses_plugin_services_and_controllers(monkeypatch):
    plugin_service = PluginService()
    captured: dict[str, object] = {}

    def plugin_controller(_stop_signal):
        return None

    monkeypatch.setattr(server, "_obs_initialized", True)
    monkeypatch.setattr(server, "get_available_services", lambda: {"agents": plugin_service})
    monkeypatch.setattr(server, "get_available_controllers", lambda: {"agents-deployment": plugin_controller})
    monkeypatch.setattr(server, "order_services_by_dependencies", lambda services: services)

    def fake_create_app(services, controller_run_funcs=None, _http_client=None):
        captured["services"] = services
        captured["controller_run_funcs"] = controller_run_funcs
        return FastAPI()

    monkeypatch.setattr(server, "create_app", fake_create_app)

    server.create_default_app()

    assert captured["services"] == [plugin_service]
    assert captured["controller_run_funcs"] == {"agents-deployment": plugin_controller}


def test_create_app_marks_mounted_services_as_local(monkeypatch):
    platform_cfg = _patch_platform_app_config(monkeypatch, seed_on_startup=False)
    platform_cfg.services = ""

    server.create_app(services=[PluginService()])

    assert platform_cfg.services == "agents"


def test_create_app_mounted_services_drive_sdk_local_routing_without_services_env(monkeypatch):
    monkeypatch.delenv("NMP_SERVICES", raising=False)
    monkeypatch.setenv("NMP_BASE_URL", "https://nemo-gateway:8080")
    monkeypatch.setenv("NMP_SERVICE_HOST", "127.0.0.1")
    monkeypatch.setenv("NMP_SERVICE_PORT", "8080")
    Configuration.clear_cache()
    platform_cfg = Configuration.get_platform_config()

    try:
        auth_cfg = _make_auth_config(enabled=False)
        monkeypatch.setattr(server, "get_platform_config", lambda: platform_cfg)
        monkeypatch.setattr(server, "get_auth_config", lambda: auth_cfg)

        import nmp.common.auth.middleware as auth_middleware
        from nmp.common.sdk_factory import get_platform_sdk

        monkeypatch.setattr(auth_middleware, "get_auth_config", lambda: auth_cfg)

        server.create_app(services=[PluginService()])

        sdk = get_platform_sdk()
        prepared = sdk._prepare_url("https://nemo-gateway:8080/apis/agents/v2/example")

        assert platform_cfg.services == "agents"
        assert prepared.scheme == "http"
        assert prepared.host == "127.0.0.1"
        assert prepared.port == 8080
    finally:
        Configuration.clear_cache()


def test_embedded_auth_preflight_invokes_policy_wasm_helper(monkeypatch):
    calls: list[bool] = []
    auth_cfg = AuthConfig(
        enabled=True,
        policy_decision_point_provider="embedded",
        embedded_pdp_auto_build_wasm=False,
    )

    from nmp.core.auth.app.embedded_pdp import policy_wasm

    monkeypatch.setattr(policy_wasm, "ensure_embedded_policy_wasm", lambda *, auto_build: calls.append(auto_build))

    server.preflight_embedded_auth_policy_wasm(auth_cfg)

    assert calls == [False]


@pytest.mark.parametrize(
    "auth_cfg",
    [
        AuthConfig(enabled=False, policy_decision_point_provider="embedded"),
        AuthConfig(enabled=True, policy_decision_point_provider="opa"),
    ],
)
def test_embedded_auth_preflight_skips_when_not_needed(auth_cfg, monkeypatch):
    calls: list[bool] = []

    from nmp.core.auth.app.embedded_pdp import policy_wasm

    monkeypatch.setattr(policy_wasm, "ensure_embedded_policy_wasm", lambda *, auto_build: calls.append(auto_build))

    server.preflight_embedded_auth_policy_wasm(auth_cfg)

    assert calls == []


def test_run_server_runs_embedded_auth_preflight():
    auth_cfg = _make_auth_config(enabled=True)
    calls: list[AuthConfig] = []
    with (
        patch("nmp.platform_runner.server.get_auth_config", return_value=auth_cfg),
        patch(
            "nmp.platform_runner.server.preflight_embedded_auth_policy_wasm", side_effect=lambda cfg: calls.append(cfg)
        ),
        patch("nmp.platform_runner.server.create_app", return_value=FastAPI()) as create_app,
        patch("nmp.platform_runner.server.setup_fastapi_instrumentations"),
        patch("nmp.platform_runner.server.uvicorn.run") as uvicorn_run,
    ):
        server.run_server(services=[], host="127.0.0.1", port=9999)

    assert calls == [auth_cfg]
    create_app.assert_called_once_with([])
    uvicorn_run.assert_called_once()


def test_create_default_app_raises_for_unknown_service_from_env(monkeypatch):
    monkeypatch.setattr(server, "_obs_initialized", True)
    monkeypatch.setenv("NMP_SERVICES", "missing-service")
    monkeypatch.setattr(server, "get_available_services", lambda: {})
    monkeypatch.setattr(server, "get_available_controllers", lambda: {})

    with pytest.raises(
        ValueError, match="Unknown service 'missing-service' requested via NMP_SERVICES='missing-service'"
    ):
        server.create_default_app()


def test_create_default_app_raises_for_unknown_controller_from_env(monkeypatch):
    monkeypatch.setattr(server, "_obs_initialized", True)
    monkeypatch.delenv("NMP_SERVICES", raising=False)
    monkeypatch.setenv("NMP_CONTROLLERS", "missing-controller")
    monkeypatch.setattr(server, "get_available_services", lambda: {})
    monkeypatch.setattr(server, "get_available_controllers", lambda: {})

    with pytest.raises(
        ValueError,
        match="Unknown controller 'missing-controller' requested via NMP_CONTROLLERS='missing-controller'",
    ):
        server.create_default_app()


def _make_platform_config_mock(*, redirect_root_to_studio: bool = True) -> MagicMock:
    cfg = MagicMock()
    cfg.seed_on_startup = False
    cfg.redirect_root_to_studio = redirect_root_to_studio
    return cfg


def test_create_app_without_seed_on_startup_keeps_health_ready_unchanged(monkeypatch):
    _patch_platform_app_config(monkeypatch, seed_on_startup=False)

    with TestClient(server.create_app(services=[])) as client:
        response = client.get("/health/ready")
        status = client.get("/status").json()

    assert response.status_code == 200
    assert "platform-seed" not in status["services"]["ready"]
    assert all(item["name"] != "platform-seed" for item in status["services"]["not_ready"])


def test_create_app_with_seed_on_startup_blocks_readiness_until_seed_completes(monkeypatch):
    _patch_platform_app_config(monkeypatch, seed_on_startup=True)
    started = threading.Event()
    release = threading.Event()

    async def fake_seed() -> bool:
        started.set()
        await asyncio.to_thread(release.wait)
        return True

    monkeypatch.setitem(sys.modules, "nmp.platform_seed", SimpleNamespace(run_platform_seed_from_startup=fake_seed))

    with TestClient(server.create_app(services=[])) as client:
        assert started.wait(timeout=2)
        response = client.get("/health/ready")
        assert response.status_code == 503

        status = client.get("/status").json()
        assert {"name": "platform-seed", "message": "pending"} in status["services"]["not_ready"]

        release.set()
        response = _wait_for_response(client, "/health/ready", 200)

    assert response is not None
    assert response.status_code == 200


def test_create_app_with_failed_seed_keeps_health_not_ready(monkeypatch):
    _patch_platform_app_config(monkeypatch, seed_on_startup=True)

    async def fake_seed() -> bool:
        return False

    monkeypatch.setitem(sys.modules, "nmp.platform_seed", SimpleNamespace(run_platform_seed_from_startup=fake_seed))

    with TestClient(server.create_app(services=[])) as client:
        response = _wait_for_response(client, "/health/ready", 503)
        status = client.get("/status").json()

    assert response is not None
    assert response.status_code == 503
    assert {"name": "platform-seed", "message": "platform seed failed"} in status["services"]["not_ready"]


def test_create_app_with_missing_seed_package_keeps_health_not_ready(monkeypatch):
    _patch_platform_app_config(monkeypatch, seed_on_startup=True)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "nmp.platform_seed":
            raise ImportError("missing platform seed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with TestClient(server.create_app(services=[])) as client:
        response = client.get("/health/ready")
        status = client.get("/status").json()

    assert response.status_code == 503
    assert {"name": "platform-seed", "message": "platform seed is not installed"} in status["services"]["not_ready"]


@pytest.mark.parametrize("auth_enabled", [True, False])
@pytest.mark.parametrize("method", ["get", "head"])
def test_root_redirects_to_studio(auth_enabled, method):
    auth_cfg = _make_auth_config(enabled=auth_enabled)
    with (
        patch("nmp.platform_runner.server.get_platform_config", return_value=_make_platform_config_mock()),
        patch("nmp.platform_runner.server.get_auth_config", return_value=auth_cfg),
        patch("nmp.common.auth.middleware.get_auth_config", return_value=auth_cfg),
    ):
        app = server.create_app(services=[])
        client = TestClient(app, follow_redirects=False)
        response = getattr(client, method)("/")

    assert response.status_code == 301
    assert response.headers["location"] == "/studio"


def test_root_returns_ok_when_redirect_disabled():
    auth_cfg = _make_auth_config(enabled=False)
    with (
        patch(
            "nmp.platform_runner.server.get_platform_config",
            return_value=_make_platform_config_mock(redirect_root_to_studio=False),
        ),
        patch("nmp.platform_runner.server.get_auth_config", return_value=auth_cfg),
        patch("nmp.common.auth.middleware.get_auth_config", return_value=auth_cfg),
    ):
        app = server.create_app(services=[])
        client = TestClient(app, follow_redirects=False)
        response = client.get("/")

    assert response.status_code == 200


def test_non_get_root_still_requires_auth():
    auth_cfg = _make_auth_config(enabled=True)
    with (
        patch("nmp.platform_runner.server.get_platform_config", return_value=_make_platform_config_mock()),
        patch("nmp.platform_runner.server.get_auth_config", return_value=auth_cfg),
        patch("nmp.common.auth.middleware.get_auth_config", return_value=auth_cfg),
        patch("nmp.common.auth.client.AuthClient.authorize_request", return_value=MagicMock(allowed=False)),
    ):
        app = server.create_app(services=[])
        client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
        response = client.post("/")

    assert response.status_code == 401
