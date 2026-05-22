# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``AgentDeploymentController`` startup / health-check transitions.

Pin the contracts callers depend on:

- ``_start_deployment`` writes the runtime fields (status, pid, port,
  endpoint) onto the entity but does NOT propagate the runner's host-bound
  ``log_path`` — the entity is backend-agnostic and the path is meaningful
  only on the platform host.
- ``_check_health`` gives precedence to subprocess-exit over a successful
  health probe, so a dead process is reported as failed even if a stale
  ``/health`` response would otherwise pass.
"""

from __future__ import annotations

import time
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from nemo_agents_plugin.config import ControllerConfig
from nemo_agents_plugin.entities import AgentDeployment
from nemo_agents_plugin.runner.backend import DeploymentInfo
from nemo_agents_plugin.runner.controller import AgentDeploymentController


def _make_controller() -> tuple[AgentDeploymentController, Any]:
    """Build a controller with stubbed backend / entities / save.

    Returns the controller plus an ``Any``-typed alias of its backend mock,
    so tests can attach :class:`AsyncMock` attributes without fighting the
    typed ``RunnerBackend`` protocol.
    """
    ctrl = AgentDeploymentController()
    backend = MagicMock()
    backend.delete_deployment = AsyncMock()
    # Bypass on_startup() — wire stubs directly.
    ctrl._backend = backend
    ctrl._entities = MagicMock()
    ctrl._controller_config = ControllerConfig(health_check_timeout_seconds=120)
    ctrl._save = AsyncMock()  # type: ignore[method-assign]
    return ctrl, cast(Any, backend)


# ---------------------------------------------------------------------------
# _start_deployment writes runtime fields without leaking the host log path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_deployment_writes_runtime_fields_to_entity() -> None:
    """Status / pid / port / endpoint are copied; ``log_path`` is NOT.

    The entity is the public, backend-agnostic schema served by the agents
    API.  The runner backend's ``log_path`` is a host-bound implementation
    detail of the in-memory backend and must not appear on the entity.
    The CLI computes the path itself from a shared convention.
    """
    ctrl, backend = _make_controller()
    backend.allocate_port = MagicMock(return_value=49200)
    backend.create_deployment = AsyncMock(
        return_value=DeploymentInfo(
            name="dep-1",
            status="starting",
            port=49200,
            pid=4242,
            endpoint="http://127.0.0.1:49200",
            log_path="/var/data/nemo/agents/system/dep-1.log",
        )
    )
    dep = AgentDeployment(name="dep-1", workspace="default", agent="calc", status="pending")

    await ctrl._start_deployment(dep)

    assert dep.status == "starting"
    assert dep.pid == 4242
    assert dep.port == 49200
    assert dep.endpoint == "http://127.0.0.1:49200"
    assert dep.error == ""
    # The entity must remain free of host-bound fields.
    assert not hasattr(dep, "log_path") or getattr(dep, "log_path", "") == ""


# ---------------------------------------------------------------------------
# _check_health: dead process takes precedence over health probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_marks_failed_when_subprocess_exited() -> None:
    """If ``get_deployment_status`` reports a dead subprocess, mark failed.

    Pins the short-circuit: even if the health probe would succeed (e.g. a
    stale port that briefly opened before the process exited), a dead
    subprocess wins.  Without this contract a deploy could be reported
    ``running`` while the process has actually died.
    """
    ctrl, backend = _make_controller()
    backend.get_deployment_status = AsyncMock(
        return_value=DeploymentInfo(
            name="dep-1",
            status="failed",
            error="Process exited with code 1",
        )
    )
    backend.health_check = AsyncMock(return_value=True)  # would otherwise lie
    dep = AgentDeployment(
        name="dep-1",
        workspace="default",
        agent="calc",
        status="starting",
        endpoint="http://127.0.0.1:49200",
    )
    ctrl._starting_since["dep-1"] = time.monotonic()

    await ctrl._check_health(dep)

    assert dep.status == "failed"
    assert "exited with code 1" in dep.error
    # health_check should not have been queried — the dead process check
    # short-circuits the function before reaching it.
    backend.health_check.assert_not_called()


@pytest.mark.asyncio
async def test_check_health_marks_running_when_healthy() -> None:
    """Backward behaviour: a healthy process flips to ``running``."""
    ctrl, backend = _make_controller()
    backend.get_deployment_status = AsyncMock(return_value=DeploymentInfo(name="dep-1", status="starting"))
    backend.health_check = AsyncMock(return_value=True)
    dep = AgentDeployment(
        name="dep-1",
        workspace="default",
        agent="calc",
        status="starting",
        endpoint="http://127.0.0.1:49200",
    )
    ctrl._starting_since["dep-1"] = time.monotonic()

    await ctrl._check_health(dep)

    assert dep.status == "running"
