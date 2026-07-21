# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nmp.common.config import AuthConfig
from nmp.common.config.base import OIDCConfig
from nmp.common.service import Service
from nmp.platform_runner import config as runner_config
from nmp.platform_runner import server


class DummyService(Service):
    def __init__(self, name: str = "models") -> None:
        super().__init__(name=name, module_name="test.sidecars")

    def get_routers(self):
        return []


def _dummy_sidecar(_stop_signal: threading.Event) -> None:
    return None


def _patch_runner_discovery(
    monkeypatch: pytest.MonkeyPatch,
    *,
    services: dict[str, Service] | None = None,
    controllers: dict[str, Callable[[threading.Event], object]] | None = None,
    sidecars: dict[str, Callable[[threading.Event], object]] | None = None,
) -> None:
    services = services if services is not None else {"models": DummyService("models")}
    controllers = controllers if controllers is not None else {}
    sidecars = sidecars if sidecars is not None else {"adapters": _dummy_sidecar}

    monkeypatch.setattr(runner_config, "get_available_services", lambda: services)
    monkeypatch.setattr(runner_config, "get_available_controllers", lambda: controllers)
    monkeypatch.setattr(
        runner_config,
        "get_service_groups",
        lambda _available: {"all": list(services), "core": list(services), "api": []},
    )
    monkeypatch.setattr(
        runner_config, "get_controller_groups", lambda _available: {"all": list(controllers), "core": list(controllers)}
    )
    monkeypatch.setattr(runner_config, "get_default_controllers", lambda _groups: list(controllers))
    monkeypatch.setattr(runner_config, "AVAILABLE_SIDECARS", sidecars)
    monkeypatch.setattr("nmp.platform_runner.registry.AVAILABLE_SIDECARS", sidecars)
    monkeypatch.setattr(server, "AVAILABLE_SIDECARS", sidecars, raising=False)
    monkeypatch.setattr(server, "order_services_by_dependencies", lambda service_instances: service_instances)


def test_models_service_resolves_adapters_sidecar_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner_discovery(monkeypatch)

    resolved = runner_config.resolve_run_configuration(
        runner_config.PlatformAppConfig(services=["models"], controllers=[])
    )

    assert resolved.services == {"models"}
    assert resolved.sidecars == {"adapters"}


def test_explicit_sidecar_can_run_without_services(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner_discovery(monkeypatch)

    resolved = runner_config.resolve_run_configuration(
        runner_config.PlatformAppConfig(services=[], controllers=[], sidecars=["adapters"])
    )

    assert resolved.services == set()
    assert resolved.controllers == set()
    assert resolved.sidecars == {"adapters"}


def _auth_config(enabled: bool = False) -> AuthConfig:
    return AuthConfig(
        enabled=enabled,
        policy_decision_point_base_url="http://localhost:8181",
        oidc=OIDCConfig(enabled=False),
    )


def _sidecar_with_events(started: threading.Event, stopped: threading.Event) -> Callable[[threading.Event], None]:
    def run(stop_signal: threading.Event) -> None:
        started.set()
        stop_signal.wait(timeout=5.0)
        stopped.set()

    return run


def test_create_app_starts_and_stops_dummy_sidecar_with_lifespan() -> None:
    started = threading.Event()
    stopped = threading.Event()

    with (
        patch("nmp.platform_runner.server.get_platform_config") as platform_config,
        patch("nmp.platform_runner.server.get_auth_config", return_value=_auth_config(False)),
        patch("nmp.common.auth.middleware.get_auth_config", return_value=_auth_config(False)),
    ):
        platform_config.return_value.seed_on_startup = False
        platform_config.return_value.redirect_root_to_studio = False
        app = server.create_app(
            services=[],
            controller_run_funcs={"adapters": _sidecar_with_events(started, stopped)},
        )
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            assert started.wait(timeout=1.0)
            assert client.get("/").status_code == 200

    assert stopped.wait(timeout=1.0)


def test_build_platform_app_loads_dependent_sidecar_into_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    stopped = threading.Event()
    _patch_runner_discovery(monkeypatch, sidecars={"adapters": _sidecar_with_events(started, stopped)})

    with (
        patch("nmp.platform_runner.server.get_platform_config") as platform_config,
        patch("nmp.platform_runner.server.get_auth_config", return_value=_auth_config(False)),
        patch("nmp.common.auth.middleware.get_auth_config", return_value=_auth_config(False)),
    ):
        platform_config.return_value.seed_on_startup = False
        platform_config.return_value.redirect_root_to_studio = False
        app = server.build_platform_app(runner_config.PlatformAppConfig(services=["models"], controllers=[]), env={})
        from fastapi.testclient import TestClient

        with TestClient(app) as client:
            assert started.wait(timeout=1.0)
            assert client.get("/").status_code == 200

    assert stopped.wait(timeout=1.0)


def test_build_platform_app_rejects_controller_sidecar_name_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runner_discovery(
        monkeypatch,
        controllers={"adapters": _dummy_sidecar},
        sidecars={"adapters": _dummy_sidecar},
    )

    with pytest.raises(ValueError, match="Controller/sidecar name collision: adapters"):
        server.build_platform_app(
            runner_config.PlatformAppConfig(controllers=["adapters"], sidecars=["adapters"]),
            env={},
        )


def test_real_adapters_sidecar_entrypoint_starts_and_stops_with_required_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from nmp.core.models.sidecars.adapters import main as adapters_main

    started = threading.Event()
    stopped = threading.Event()
    manager = MagicMock()

    class FakeLoop:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            started.set()

        def stop(self) -> None:
            stopped.set()

        def join(self) -> None:
            return None

    lora_dir = tmp_path / "loras"
    monkeypatch.setenv("NIM_PEFT_SOURCE", str(lora_dir))
    monkeypatch.setenv("NMP_MODEL_ENTITY_WORKSPACE", "default")
    monkeypatch.setenv("NMP_MODEL_ENTITY_NAME", "test-model")
    monkeypatch.setenv("NIM_PEFT_REFRESH_INTERVAL", "30")
    monkeypatch.delenv("VLLM_ENDPOINT", raising=False)

    monkeypatch.setattr(adapters_main, "get_platform_config", lambda: MagicMock(base_url="http://platform.local"))
    monkeypatch.setattr(adapters_main, "get_platform_sdk", lambda **_kwargs: MagicMock())
    monkeypatch.setattr(adapters_main.asyncio, "new_event_loop", lambda: MagicMock())
    monkeypatch.setattr(adapters_main, "Loop", FakeLoop)
    monkeypatch.setattr(adapters_main, "TimedLoopWaiter", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(adapters_main.ControllerManager, "get_instance", classmethod(lambda _cls: manager))

    stop_signal = threading.Event()
    thread = threading.Thread(target=adapters_main.run, args=(stop_signal,), daemon=True)
    try:
        thread.start()

        assert started.wait(timeout=1.0)
        manager.register.assert_called_once()
        assert manager.register.call_args.args[0] == "adapters_controller"

        stop_signal.set()
        thread.join(timeout=1.0)

        assert not thread.is_alive()
        assert stopped.is_set()
    finally:
        stop_signal.set()
        thread.join(timeout=1.0)
        adapters_main.adapters_controller_monitored = None
