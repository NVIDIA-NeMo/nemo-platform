# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the service-principal auth-proxy sidecar forwarder."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from nmp.common.auth.workload_proxy import main as workload_proxy_main
from nmp.common.auth.workload_proxy.main import build_app
from nmp.common.controller import ControllerManager, Loop


@respx.mock
def test_forward_stamps_service_principal_and_preserves_path() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.post(f"{upstream}/apis/inference-gateway/v2/workspaces/default/openai/-/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    app = build_app(base_url=upstream, principal="agents")
    client = TestClient(app)

    resp = client.post(
        "/apis/inference-gateway/v2/workspaces/default/openai/-/v1/chat/completions",
        json={"model": "m", "messages": []},
        headers={"authorization": "Bearer not-used"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert route.called
    sent = route.calls.last.request
    # The proxy sets the service-principal identity and drops the placeholder auth.
    assert sent.headers["x-nmp-principal-id"] == "service:agents"
    assert "authorization" not in {k.lower() for k in sent.headers}


@respx.mock
def test_forward_stamps_on_behalf_of_when_configured() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(200, json={}))
    app = build_app(base_url=upstream, principal="agents", on_behalf_of="user:alice")
    client = TestClient(app)

    client.get("/apis/entities/v2/workspaces")

    sent = route.calls.last.request
    # Service principal clears the route gate; on-behalf-of narrows access to the creator.
    assert sent.headers["x-nmp-principal-id"] == "service:agents"
    assert sent.headers["x-nmp-principal-on-behalf-of"] == "user:alice"


@respx.mock
def test_forward_omits_on_behalf_of_when_not_configured() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(200, json={}))
    app = build_app(base_url=upstream, principal="agents")
    client = TestClient(app)

    client.get("/apis/entities/v2/workspaces")

    sent = route.calls.last.request
    assert "x-nmp-principal-on-behalf-of" not in {k.lower() for k in sent.headers}


@respx.mock
def test_forward_strips_inbound_on_behalf_of_to_prevent_spoofing() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(200, json={}))
    # The delegated identity is baked in at deploy time; a co-located workload must
    # not be able to override it (or inject one when none is configured) via headers.
    app = build_app(base_url=upstream, principal="agents", on_behalf_of="user:alice")
    client = TestClient(app)

    client.get(
        "/apis/entities/v2/workspaces",
        headers={
            "x-nmp-principal-id": "service:platform",
            "x-nmp-principal-on-behalf-of": "user:attacker",
            # Companion metadata must not be smuggled onto our stamped OBO id:
            # the platform derives effective groups/email from these and feeds
            # them to the PDP, so attacker-chosen values would escalate.
            "x-nmp-principal-on-behalf-of-email": "attacker@evil.test",
            "x-nmp-principal-on-behalf-of-groups": "platform-admins",
        },
    )

    sent = route.calls.last.request
    sent_keys = {k.lower() for k in sent.headers}
    assert sent.headers["x-nmp-principal-id"] == "service:agents"
    assert sent.headers["x-nmp-principal-on-behalf-of"] == "user:alice"
    # The inbound companion headers are dropped (we stamp only the OBO id).
    assert "x-nmp-principal-on-behalf-of-email" not in sent_keys
    assert "x-nmp-principal-on-behalf-of-groups" not in sent_keys


@respx.mock
def test_forward_strips_inbound_on_behalf_of_when_none_configured() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(200, json={}))
    app = build_app(base_url=upstream, principal="agents")
    client = TestClient(app)

    client.get(
        "/apis/entities/v2/workspaces",
        headers={
            "x-nmp-principal-on-behalf-of": "user:attacker",
            "x-nmp-principal-on-behalf-of-email": "attacker@evil.test",
            "x-nmp-principal-on-behalf-of-groups": "platform-admins",
        },
    )

    sent = route.calls.last.request
    sent_keys = {k.lower() for k in sent.headers}
    assert "x-nmp-principal-on-behalf-of" not in sent_keys
    assert "x-nmp-principal-on-behalf-of-email" not in sent_keys
    assert "x-nmp-principal-on-behalf-of-groups" not in sent_keys


@respx.mock
def test_forward_normalizes_bare_principal_name() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(200, json={}))
    # Already-prefixed principal is passed through unchanged.
    app = build_app(base_url=upstream, principal="service:models")
    client = TestClient(app)
    client.get("/apis/entities/v2/workspaces")
    assert route.calls.last.request.headers["x-nmp-principal-id"] == "service:models"


@respx.mock
def test_forward_passes_through_upstream_status() -> None:
    upstream = "http://nemo-platform-api:8080"
    respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(403, json={"detail": "no"}))
    app = build_app(base_url=upstream, principal="agents")
    client = TestClient(app)

    resp = client.get("/apis/entities/v2/workspaces")
    assert resp.status_code == 403


def test_healthz_does_not_require_upstream() -> None:
    app = build_app(base_url="http://nemo-platform-api:8080", principal="agents")
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_lifespan_closes_upstream_client() -> None:
    # Entering TestClient as a context manager runs the lifespan; the shared
    # httpx client's connection pool must be closed on shutdown.
    created: list[httpx.AsyncClient] = []
    real_async_client = httpx.AsyncClient

    def _tracking_client(*args, **kwargs) -> httpx.AsyncClient:
        client = real_async_client(*args, **kwargs)
        created.append(client)
        return client

    with patch("nmp.common.auth.workload_proxy.main.httpx.AsyncClient", side_effect=_tracking_client):
        app = build_app(base_url="http://nemo-platform-api:8080", principal="agents")

    assert len(created) == 1
    upstream_client = created[0]
    with TestClient(app) as test_client:
        assert test_client.get("/healthz").status_code == 200
        assert upstream_client.is_closed is False
    assert upstream_client.is_closed is True


@pytest.fixture(autouse=True)
def _reset_controller_manager() -> Iterator[None]:
    ControllerManager._instance = None
    yield
    ControllerManager._instance = None


def test_run_registers_and_unregisters_healthy_loop_for_health_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose a running auth-proxy as healthy and remove it on shutdown."""
    monkeypatch.setenv("NMP_AUTH_PROXY_PRINCIPAL", "agents")
    monkeypatch.setenv("NEMO_BASE_URL", "http://nemo-platform-api:8080")

    server_started = threading.Event()

    class _FakeServer:
        def __init__(self, config: object) -> None:
            self.should_exit = False

        def run(self) -> None:
            server_started.set()
            while not self.should_exit:
                threading.Event().wait(timeout=0.05)

    monkeypatch.setattr(workload_proxy_main.uvicorn, "Server", _FakeServer)

    manager = ControllerManager.get_instance()
    for _ in range(2):
        server_started.clear()
        stop_signal = threading.Event()
        run_thread = threading.Thread(target=workload_proxy_main.run, args=(stop_signal,), daemon=True)
        run_thread.start()
        try:
            assert server_started.wait(timeout=2)

            def _registered() -> bool:
                return "auth-proxy" in manager.get_all_loops()

            assert _wait_until(_registered)
            assert _wait_until(lambda: manager.validate_all_healthy() == (True, {"auth-proxy": True}))
        finally:
            stop_signal.set()
            run_thread.join(timeout=5)
        assert not run_thread.is_alive()
        assert manager.validate_all_healthy() == (True, {})


def test_run_leaves_controller_tracked_when_uvicorn_thread_outlives_shutdown(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Keep a hung Uvicorn server tracked until it exits."""
    monkeypatch.setenv("NMP_AUTH_PROXY_PRINCIPAL", "agents")
    monkeypatch.setenv("NEMO_BASE_URL", "http://nemo-platform-api:8080")
    monkeypatch.setattr(workload_proxy_main, "_UVICORN_JOIN_TIMEOUT_SECONDS", 0.05)

    server_started = threading.Event()
    hang_forever = threading.Event()

    class _HangingFakeServer:
        def __init__(self, config: object) -> None:
            self.should_exit = False

        def run(self) -> None:
            server_started.set()
            hang_forever.wait(timeout=5)

    monkeypatch.setattr(workload_proxy_main.uvicorn, "Server", _HangingFakeServer)

    manager = ControllerManager.get_instance()
    stop_signal = threading.Event()
    run_thread = threading.Thread(target=workload_proxy_main.run, args=(stop_signal,), daemon=True)
    run_thread.start()
    try:
        assert server_started.wait(timeout=2)
        assert _wait_until(lambda: "auth-proxy" in manager.get_all_loops())

        with caplog.at_level(logging.WARNING, logger="nmp.common.controller.controller_manager"):
            stop_signal.set()
            run_thread.join(timeout=5)
        assert not run_thread.is_alive()

        assert "auth-proxy" in manager.get_all_loops()
        assert "Leaving health tracking in place for 'auth-proxy'" in caplog.text
    finally:
        hang_forever.set()

    assert _wait_until(lambda: "auth-proxy" not in manager.get_all_loops())

    restarted_server = threading.Event()

    class _RestartedFakeServer:
        def __init__(self, config: object) -> None:
            self.should_exit = False

        def run(self) -> None:
            restarted_server.set()
            while not self.should_exit:
                threading.Event().wait(timeout=0.001)

    monkeypatch.setattr(workload_proxy_main.uvicorn, "Server", _RestartedFakeServer)

    second_stop_signal = threading.Event()
    second_run_thread = threading.Thread(
        target=workload_proxy_main.run,
        args=(second_stop_signal,),
        daemon=True,
    )
    second_run_thread.start()
    try:
        assert restarted_server.wait(timeout=2)
        assert _wait_until(lambda: manager.validate_all_healthy() == (True, {"auth-proxy": True}))
    finally:
        second_stop_signal.set()
        second_run_thread.join(timeout=5)

    assert not second_run_thread.is_alive()
    assert manager.validate_all_healthy() == (True, {})


def test_run_setup_failure_before_server_start_is_visible_as_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report auth-proxy setup failures through controller health."""
    monkeypatch.delenv("NMP_AUTH_PROXY_PRINCIPAL", raising=False)

    manager = ControllerManager.get_instance()
    stop_signal = threading.Event()

    with pytest.raises(RuntimeError, match="NMP_AUTH_PROXY_PRINCIPAL"):
        workload_proxy_main.run(stop_signal)

    all_healthy, status = manager.validate_all_healthy()
    assert all_healthy is False
    assert status.get("auth-proxy") is False


def test_run_registration_failure_never_starts_server_and_remains_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject duplicate tracking before starting Uvicorn."""
    monkeypatch.setenv("NMP_AUTH_PROXY_PRINCIPAL", "agents")
    monkeypatch.setenv("NEMO_BASE_URL", "http://nemo-platform-api:8080")
    server_started = threading.Event()

    class _FakeServer:
        def __init__(self, config: object) -> None:
            self.should_exit = False

        def run(self) -> None:
            server_started.set()
            while not self.should_exit:
                threading.Event().wait(timeout=0.01)

    monkeypatch.setattr(workload_proxy_main.uvicorn, "Server", _FakeServer)
    manager = ControllerManager.get_instance()

    def _fail_registration(_name: str, _loop: object) -> None:
        raise ValueError("duplicate")

    monkeypatch.setattr(manager, "register", _fail_registration)

    with pytest.raises(ValueError, match="duplicate"):
        workload_proxy_main.run(threading.Event())

    assert not server_started.wait(timeout=0.5)
    assert manager.validate_all_healthy() == (False, {"auth-proxy": False})


def test_run_uvicorn_thread_start_failure_removes_registered_loop_and_remains_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NMP_AUTH_PROXY_PRINCIPAL", "agents")
    monkeypatch.setenv("NEMO_BASE_URL", "http://nemo-platform-api:8080")

    real_start = threading.Thread.start

    def _start(thread: threading.Thread) -> None:
        if thread.name != "auth-proxy-uvicorn":
            real_start(thread)
        else:
            raise RuntimeError("thread start failed")

    monkeypatch.setattr(threading.Thread, "start", _start)
    manager = ControllerManager.get_instance()

    with pytest.raises(RuntimeError, match="thread start failed"):
        workload_proxy_main.run(threading.Event())

    assert manager.get_all_loops() == {}
    assert manager.validate_all_healthy() == (False, {"auth-proxy": False})


def test_run_health_loop_start_failure_tracks_uvicorn_until_delayed_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NMP_AUTH_PROXY_PRINCIPAL", "agents")
    monkeypatch.setenv("NEMO_BASE_URL", "http://nemo-platform-api:8080")
    monkeypatch.setattr(workload_proxy_main, "_UVICORN_JOIN_TIMEOUT_SECONDS", 0.05)

    server_started = threading.Event()
    release_server = threading.Event()

    class _HangingFakeServer:
        def __init__(self, config: object) -> None:
            self.should_exit = False

        def run(self) -> None:
            server_started.set()
            release_server.wait(timeout=5)

    def _fail_health_loop_start(_loop: Loop) -> None:
        raise RuntimeError("health loop start failed")

    monkeypatch.setattr(workload_proxy_main.uvicorn, "Server", _HangingFakeServer)
    monkeypatch.setattr(Loop, "start", _fail_health_loop_start)
    manager = ControllerManager.get_instance()

    try:
        with pytest.raises(RuntimeError, match="health loop start failed"):
            workload_proxy_main.run(threading.Event())

        assert server_started.wait(timeout=2)
        assert "auth-proxy" in manager.get_all_loops()
        assert manager.validate_all_healthy() == (False, {"auth-proxy": False})
    finally:
        release_server.set()

    assert _wait_until(lambda: manager.validate_all_healthy() == (True, {}))


def _wait_until(predicate: Callable[[], bool], timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()
