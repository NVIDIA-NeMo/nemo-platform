# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from nemo_agents_plugin.fabric import session_registry
from nemo_agents_plugin.fabric.session_registry import (
    FabricSessionAlreadyExistsError,
    FabricSessionNotFoundError,
    FabricSessionRegistry,
    FabricSessionRegistryClosedError,
)


@pytest.mark.asyncio
async def test_register_generates_opaque_session_id() -> None:
    registry = FabricSessionRegistry()
    runtime = object()

    session = await registry.register(cast(Any, runtime))

    assert uuid.UUID(session.session_id)
    assert session.runtime is runtime
    assert session.created_at == session.last_accessed_at
    assert await registry.count() == 1


@pytest.mark.asyncio
async def test_each_session_has_an_independent_invocation_lock() -> None:
    registry = FabricSessionRegistry()

    first = await registry.register(cast(Any, object()), session_id="session-1")
    second = await registry.register(cast(Any, object()), session_id="session-2")

    assert first.invocation_lock is not second.invocation_lock


@pytest.mark.asyncio
async def test_get_returns_session_and_updates_last_accessed_at(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([10.0, 20.0])
    monkeypatch.setattr(session_registry, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, object()), session_id="session-1")

    resolved = await registry.get("session-1")

    assert resolved is session
    assert resolved.created_at == 10.0
    assert resolved.last_accessed_at == 20.0


@pytest.mark.asyncio
async def test_register_rejects_duplicate_session_id() -> None:
    registry = FabricSessionRegistry()
    await registry.register(cast(Any, object()), session_id="session-1")

    with pytest.raises(FabricSessionAlreadyExistsError, match="already registered"):
        await registry.register(cast(Any, object()), session_id="session-1")


@pytest.mark.asyncio
async def test_get_rejects_unknown_session_id() -> None:
    registry = FabricSessionRegistry()

    with pytest.raises(FabricSessionNotFoundError, match="was not found"):
        await registry.get("missing")


@pytest.mark.asyncio
async def test_remove_returns_session_and_is_idempotent() -> None:
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, object()), session_id="session-1")

    assert await registry.remove("session-1") is session
    assert await registry.remove("session-1") is None
    assert await registry.count() == 0


@pytest.mark.asyncio
async def test_refresh_activity_updates_registered_session(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([10.0, 20.0])
    monkeypatch.setattr(session_registry, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, object()), session_id="session-1")

    await registry.refresh_activity(session)

    assert session.last_accessed_at == 20.0


@pytest.mark.asyncio
async def test_remove_expired_removes_only_idle_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_registry, "time", SimpleNamespace(monotonic=lambda: 100.0))
    registry = FabricSessionRegistry()
    expired = await registry.register(cast(Any, object()), session_id="expired")
    active = await registry.register(cast(Any, object()), session_id="active")
    recent = await registry.register(cast(Any, object()), session_id="recent")
    expired.last_accessed_at = 10.0
    active.last_accessed_at = 10.0
    recent.last_accessed_at = 90.0

    await active.invocation_lock.acquire()
    try:
        removed = await registry.remove_expired(idle_timeout_seconds=30.0)
    finally:
        active.invocation_lock.release()

    assert removed == [expired]
    assert expired.closing is True
    assert active.closing is False
    assert recent.closing is False
    assert await registry.count() == 2


@pytest.mark.asyncio
async def test_drain_removes_sessions_and_rejects_new_registrations() -> None:
    registry = FabricSessionRegistry()
    first = await registry.register(cast(Any, object()), session_id="session-1")
    second = await registry.register(cast(Any, object()), session_id="session-2")

    drained = await registry.drain()

    assert drained == [first, second]
    assert first.closing is True
    assert second.closing is True
    assert await registry.count() == 0
    with pytest.raises(FabricSessionRegistryClosedError, match="registry is closed"):
        await registry.register(cast(Any, object()), session_id="session-3")
