# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the deployment controller state machine (backend + entities mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from nemo_jailbreak_detect import controller as controller_mod
from nemo_jailbreak_detect.controller import JailbreakDetectController
from nemo_jailbreak_detect.deployment.backend import DeploymentResult
from nemo_jailbreak_detect.entities import JailbreakDetectorDeployment


class _FakeBackend:
    def __init__(self, ready: bool = True) -> None:
        self._ready = ready
        self.stopped: list[str] = []

    async def ensure_started(self, spec) -> DeploymentResult:
        return DeploymentResult(handle="container-1", endpoint_url=f"http://localhost:{spec.port}")

    async def is_ready(self, endpoint_url: str, timeout: float) -> bool:
        return self._ready

    async def stop(self, handle: str) -> None:
        self.stopped.append(handle)


@pytest.fixture
def ctrl(monkeypatch) -> JailbreakDetectController:
    c = JailbreakDetectController()
    c._entities = AsyncMock()
    c._model_cache_dir = "/tmp/cache"
    c._request_timeout = 5.0
    return c


def _deployment(**kw) -> JailbreakDetectorDeployment:
    base = dict(name="jbd", workspace="default", backend="docker", port=8123)
    base.update(kw)
    return JailbreakDetectorDeployment(**base)


async def test_pending_starts_backend(ctrl, monkeypatch):
    backend = _FakeBackend()
    monkeypatch.setattr(controller_mod, "get_backend", lambda kind: backend)
    dep = _deployment(status="pending")

    await ctrl._reconcile_one(dep)

    assert dep.status == "starting"
    assert dep.handle == "container-1"
    assert dep.endpoint_url == "http://localhost:8123"
    ctrl._entities.update.assert_awaited_once()


async def test_starting_becomes_running_when_ready(ctrl, monkeypatch):
    monkeypatch.setattr(controller_mod, "get_backend", lambda kind: _FakeBackend(ready=True))
    dep = _deployment(status="starting", endpoint_url="http://localhost:8123", handle="container-1")

    await ctrl._reconcile_one(dep)

    assert dep.status == "running"
    ctrl._entities.update.assert_awaited_once()


async def test_starting_stays_when_not_ready(ctrl, monkeypatch):
    monkeypatch.setattr(controller_mod, "get_backend", lambda kind: _FakeBackend(ready=False))
    dep = _deployment(status="starting", endpoint_url="http://localhost:8123")

    await ctrl._reconcile_one(dep)

    assert dep.status == "starting"
    ctrl._entities.update.assert_not_awaited()


async def test_running_fails_on_unhealthy(ctrl, monkeypatch):
    monkeypatch.setattr(controller_mod, "get_backend", lambda kind: _FakeBackend(ready=False))
    dep = _deployment(status="running", endpoint_url="http://localhost:8123")

    await ctrl._reconcile_one(dep)

    assert dep.status == "failed"
    assert dep.last_error == "health check failed"


async def test_stopping_stops_and_deletes(ctrl, monkeypatch):
    backend = _FakeBackend()
    monkeypatch.setattr(controller_mod, "get_backend", lambda kind: backend)
    dep = _deployment(status="stopping", handle="container-1")

    await ctrl._reconcile_one(dep)

    assert backend.stopped == ["container-1"]
    ctrl._entities.delete.assert_awaited_once()
