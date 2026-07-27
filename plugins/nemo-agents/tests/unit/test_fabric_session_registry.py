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
