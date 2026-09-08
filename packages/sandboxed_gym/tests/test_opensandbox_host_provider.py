# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Readiness diagnostics of the OpenSandbox job-host provider.

These need no OpenSandbox SDK: the module keeps its SDK types under ``TYPE_CHECKING`` and builds
the driver lazily, so the provider imports and constructs from a plain checkout.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from sandboxed_gym.host.models import GymHostHandle, GymHostSpec, GymHostVolumeMount
from sandboxed_gym.host.opensandbox import OpenSandboxGymHostProvider

HEALTH_URL = "https://sandbox.example/gym-1/health"
ROLLOUT_URL = "https://sandbox.example/gym-1/rollouts/run"


@pytest.fixture
def provider() -> OpenSandboxGymHostProvider:
    return OpenSandboxGymHostProvider(connection={"domain": "x", "api_key": "k"})


def test_readiness_timeout_names_the_url_it_polled(
    provider: OpenSandboxGymHostProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scheme or port mismatch is otherwise indistinguishable from a slow sandbox.

    The host id alone cannot be turned back into the URL the poll used, so a misconfigured
    protocol reads as "the sandbox is taking too long" and sends the reader to the wrong place.
    """
    handle = GymHostHandle(host_id="gym-1", health_url=HEALTH_URL, rollout_url=ROLLOUT_URL)

    def _refuse(url: str, headers: Any) -> dict[str, Any]:
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(provider, "_get_json", _refuse)

    with pytest.raises(TimeoutError) as excinfo:
        asyncio.run(provider.wait_ready(handle, timeout_s=0.01))

    message = str(excinfo.value)
    assert HEALTH_URL in message
    # The underlying error too: knowing which URL was polled is only half of it.
    assert "connection refused" in message


def test_a_created_host_logs_the_urls_it_resolved(
    provider: OpenSandboxGymHostProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``create_host`` is the only place the resolved URLs are knowable.

    They come back from the SDK's route resolution onto a handle the caller may never print, so
    without this every downstream connectivity failure is a timeout against an address that
    appears nowhere in the logs.
    """
    routes = _Routes(health_url=HEALTH_URL, rollout_url=ROLLOUT_URL, headers={})
    monkeypatch.setattr(provider, "_provider_for_spec", lambda spec: _StubDriver())
    monkeypatch.setattr(provider, "_to_sandbox_spec", lambda spec: spec)
    monkeypatch.setattr(provider, "_resolve_routes", _returning(routes))

    with caplog.at_level(logging.INFO, logger="sandboxed_gym.host.opensandbox"):
        asyncio.run(provider.create_host(_spec()))

    assert HEALTH_URL in caplog.text
    assert ROLLOUT_URL in caplog.text
    assert "gym-1" in caplog.text


class _Routes:
    def __init__(self, *, health_url: str, rollout_url: str, headers: dict[str, str]) -> None:
        self.health_url = health_url
        self.rollout_url = rollout_url
        self.headers = headers


class _ResourceHandle:
    sandbox_id = "gym-1"
    raw = object()


class _StubDriver:
    """Stands in for the OpenSandbox SDK driver, which is the only part needing a real cluster."""

    async def create(self, spec: GymHostSpec) -> _ResourceHandle:
        return _ResourceHandle()


def _returning(routes: _Routes):
    async def _resolve(raw: Any, port: int) -> _Routes:
        return routes

    return _resolve


def _spec() -> GymHostSpec:
    return GymHostSpec(
        job_id="job-1",
        runtime_image="example/gym:latest",
        environment_mount=GymHostVolumeMount(pvc_claim="env", mount_path="/job/environment", read_only=True),
        workspace_mount=GymHostVolumeMount(pvc_claim="work", mount_path="/job/work"),
    )
