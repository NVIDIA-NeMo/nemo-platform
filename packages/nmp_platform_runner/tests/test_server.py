# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.common.config import AuthConfig
from nmp.common.config.base import OIDCConfig
from nmp.common.service import Service
from nmp.platform_runner import server


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
