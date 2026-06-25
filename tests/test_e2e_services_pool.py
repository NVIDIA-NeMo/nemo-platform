# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import httpx

import e2e.services_pool as services_pool
from e2e.services_pool import E2EServicesPool, ModuleConfigState, ServicesPoolKey


class _StubModule:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


class _ExitedProc:
    def poll(self) -> int:
        return 1


def test_acquire_for_module_preserves_auth_for_external_url(monkeypatch) -> None:
    pool = E2EServicesPool()
    module = _StubModule("e2e/test_example.py")
    pool._module_states[module.nodeid] = ModuleConfigState(
        module_id=module.nodeid,
        key=ServicesPoolKey(config_hash="abc123"),
        config_path=Path("/tmp/platform.yaml"),
        config_data={},
        config_layers=(),
        auth_enabled=True,
    )
    monkeypatch.setenv("NMP_BASE_URL", "http://external.example")

    services = pool.acquire_for_module(module)

    assert services.url == "http://external.example"
    assert services.auth_enabled is True


def test_wait_for_healthy_returns_false_immediately_when_process_has_exited(monkeypatch) -> None:
    monkeypatch.setattr(
        services_pool.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.RequestError("down")),
    )
    monkeypatch.setattr(services_pool.time, "sleep", lambda _: (_ for _ in ()).throw(AssertionError("slept")))

    assert services_pool._wait_for_healthy("http://example.com", _ExitedProc(), timeout=0.1) is False


def test_wait_for_auth_ready_returns_false_immediately_when_process_has_exited(monkeypatch) -> None:
    monkeypatch.setattr(
        services_pool.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.RequestError("down")),
    )
    monkeypatch.setattr(services_pool.time, "sleep", lambda _: (_ for _ in ()).throw(AssertionError("slept")))

    assert services_pool._wait_for_auth_ready("http://example.com", _ExitedProc(), timeout=0.1) is False
