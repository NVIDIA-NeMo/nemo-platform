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
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from nemo_agents_plugin.config import AgentsConfig, ControllerConfig
from nemo_agents_plugin.entities import AgentDeployment, AgentSession, SessionStatus
from nemo_agents_plugin.runner import controller as controller_module
from nemo_agents_plugin.runner.backend import DeploymentInfo
from nemo_agents_plugin.runner.controller import AgentDeploymentController
from nemo_platform_plugin.entities.client import AsyncEntitiesClient
from nemo_platform_plugin.entity_client import NemoEntityConflictError

EXPIRATION_NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def test_agent_deployment_controller_declares_entities_dependency() -> None:
    assert AgentDeploymentController.dependencies == ["entities"]


@pytest.mark.asyncio
async def test_controller_startup_adapts_sdk_to_typed_entities_client() -> None:
    sdk = MagicMock()
    typed_client = MagicMock()
    entity_client = MagicMock()

    with (
        patch("nemo_agents_plugin.config.AgentsConfig.get", return_value=AgentsConfig()),
        patch("nemo_platform_plugin.sdk_provider.get_async_platform_sdk", return_value=sdk),
        patch(
            "nemo_platform_plugin.client.adapter.client_from_platform",
            return_value=typed_client,
        ) as mock_adapter,
        patch("nemo_platform_plugin.entities.EntityClient", return_value=entity_client) as mock_entity_client,
    ):
        controller = AgentDeploymentController()
        await controller.on_startup()

    mock_adapter.assert_called_once_with(sdk, AsyncEntitiesClient)
    mock_entity_client.assert_called_once_with(typed_client)
    assert controller._entities is entity_client


def _make_controller() -> tuple[AgentDeploymentController, Any]:
    """Build a controller with stubbed backend / entities / save.

    Returns the controller plus an ``Any``-typed alias of its backend mock,
    so tests can attach :class:`AsyncMock` attributes without fighting the
    typed ``RunnerBackend`` protocol.
    """
    ctrl = AgentDeploymentController()
    backend = MagicMock()
    backend.delete_deployment = AsyncMock()
    registry = MagicMock()
    registry.backend = backend
    registry.backend_for = MagicMock(return_value=backend)
    # Bypass on_startup() — wire stubs directly.
    ctrl._registry = registry
    ctrl._entities = MagicMock()
    ctrl._controller_config = ControllerConfig(health_check_timeout_seconds=120)
    ctrl._save = AsyncMock()  # type: ignore[method-assign]
    return ctrl, cast(Any, backend)


def _make_session(
    *,
    name: str = "session-one",
    expires_at: datetime | None = None,
    status: SessionStatus = SessionStatus.ACTIVE,
) -> AgentSession:
    session = AgentSession(
        name=name,
        workspace="default",
        deployment_id="deployment-id",
        status=status,
        expires_at=expires_at,
    )
    session._id = f"{name}-id"
    return session


@pytest.mark.asyncio
async def test_reconcile_runs_expiration_after_isolated_deployment_failures() -> None:
    ctrl, _ = _make_controller()
    first = AgentDeployment(name="first", workspace="default", agent="calc")
    second = AgentDeployment(name="second", workspace="default", agent="calc")
    ctrl.list_objects = AsyncMock(return_value=[first, second])  # type: ignore[method-assign]
    ctrl.reconcile_one = AsyncMock(side_effect=[RuntimeError("failed"), None])  # type: ignore[method-assign]
    ctrl._reconcile_expired_sessions = AsyncMock()  # type: ignore[method-assign]

    await ctrl.reconcile()

    assert ctrl.reconcile_one.await_args_list == [call(first), call(second)]
    ctrl._reconcile_expired_sessions.assert_awaited_once_with()


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
    # Startup timer is keyed by ``(workspace, name)``; ``_check_health``
    # reads from the same tuple. Asserting the key shape here catches the
    # silent string-vs-tuple drift that the prior pass surfaced.
    starting_key = ("default", "dep-1")
    assert starting_key in ctrl._starting_since


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
    ctrl._starting_since[("default", "dep-1")] = time.monotonic()

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
    ctrl._starting_since[("default", "dep-1")] = time.monotonic()

    await ctrl._check_health(dep)

    assert dep.status == "running"


# ---------------------------------------------------------------------------
# Persisted session expiration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expire_session_transitions_due_session_and_cleans_runtime() -> None:
    ctrl, _ = _make_controller()
    session = _make_session(expires_at=EXPIRATION_NOW)
    ctrl.entities.update = AsyncMock(side_effect=lambda entity: entity)

    with patch.object(controller_module, "cleanup_fabric_runtime", new_callable=AsyncMock) as cleanup:
        result = await ctrl._expire_session_if_due(session, at=EXPIRATION_NOW)

    assert result is session
    assert session.status is SessionStatus.EXPIRED
    ctrl.entities.update.assert_awaited_once_with(session)
    cleanup.assert_awaited_once_with(ctrl.entities, session)


@pytest.mark.asyncio
@pytest.mark.parametrize("expires_at", [None, EXPIRATION_NOW + timedelta(seconds=1)])
async def test_expire_session_leaves_session_before_deadline_active(expires_at: datetime | None) -> None:
    ctrl, _ = _make_controller()
    session = _make_session(expires_at=expires_at)

    with patch.object(controller_module, "cleanup_fabric_runtime", new_callable=AsyncMock) as cleanup:
        result = await ctrl._expire_session_if_due(
            session,
            at=EXPIRATION_NOW,
        )

    assert result is None
    assert session.status is SessionStatus.ACTIVE
    ctrl.entities.update.assert_not_called()
    cleanup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("refreshed_status", "deadline_delta_seconds", "expected_updates", "expected_cleanup"),
    [
        pytest.param(SessionStatus.ACTIVE, 30 * 60, 1, False, id="renewed-activity-wins"),
        pytest.param(SessionStatus.ACTIVE, -1, 2, True, id="still-due-retries"),
        pytest.param(SessionStatus.CLOSED, -1, 1, False, id="closed-wins"),
        pytest.param(SessionStatus.EXPIRED, -1, 1, True, id="concurrent-expiration-is-idempotent"),
    ],
)
async def test_expiration_conflict_resolves_from_refetched_session(
    refreshed_status: SessionStatus,
    deadline_delta_seconds: int,
    expected_updates: int,
    expected_cleanup: bool,
) -> None:
    ctrl, _ = _make_controller()
    stale = _make_session(expires_at=EXPIRATION_NOW - timedelta(seconds=2))
    refreshed = _make_session(
        expires_at=EXPIRATION_NOW + timedelta(seconds=deadline_delta_seconds),
        status=refreshed_status,
    )
    ctrl.entities.update = AsyncMock(side_effect=[NemoEntityConflictError("conflict"), refreshed])
    ctrl.entities.get_by_id = AsyncMock(return_value=refreshed)

    with patch.object(controller_module, "cleanup_fabric_runtime", new_callable=AsyncMock) as cleanup:
        result = await ctrl._expire_session_if_due(stale, at=EXPIRATION_NOW)

    assert (result is refreshed) is expected_cleanup
    expected_status = (
        SessionStatus.EXPIRED
        if refreshed_status is SessionStatus.ACTIVE and deadline_delta_seconds <= 0
        else refreshed_status
    )
    assert refreshed.status is expected_status
    assert ctrl.entities.update.await_count == expected_updates
    ctrl.entities.get_by_id.assert_awaited_once_with(AgentSession, stale.id)
    if expected_cleanup:
        cleanup.assert_awaited_once_with(ctrl.entities, refreshed)
    else:
        cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_session_listing_follows_pagination() -> None:
    ctrl, _ = _make_controller()
    first = MagicMock(data=[_make_session(name="one")])
    first.pagination = MagicMock(total_pages=2)
    second = MagicMock(data=[_make_session(name="two")])
    second.pagination = MagicMock(total_pages=2)
    ctrl.entities.list = AsyncMock(side_effect=[first, second])

    sessions = await ctrl._list_active_sessions()

    assert [session.name for session in sessions] == ["one", "two"]
    assert ctrl.entities.list.await_args_list == [
        call(
            AgentSession,
            workspace="-",
            filter_obj={"status": SessionStatus.ACTIVE.value},
            page=1,
            page_size=100,
        ),
        call(
            AgentSession,
            workspace="-",
            filter_obj={"status": SessionStatus.ACTIVE.value},
            page=2,
            page_size=100,
        ),
    ]
