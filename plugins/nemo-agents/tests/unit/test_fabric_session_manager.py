# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric import session_manager
from nemo_agents_plugin.fabric.runtime import FabricInvocationRequest, FabricRuntimeResult
from nemo_agents_plugin.fabric.session_manager import FabricSessionManager
from nemo_agents_plugin.fabric.session_registry import (
    FabricSessionNotFoundError,
    FabricSessionRegistry,
)


class _FakeRuntime:
    def __init__(self) -> None:
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeFabric:
    def __init__(self, runtime: _FakeRuntime) -> None:
        self.runtime = runtime
        self.start_calls: list[tuple[Any, Path]] = []

    async def start_runtime(self, config: Any, *, base_dir: Path) -> _FakeRuntime:
        self.start_calls.append((config, base_dir))
        return self.runtime


def _agent_config() -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "config_format": "nemo-agents-spec-v1",
            "name": "test-agent",
            "default_harness": "hermes",
            "harnesses": {
                "hermes": {
                    "kind": "hermes",
                    "model": {
                        "provider": "nvidia",
                        "model": "nvidia/test-model",
                    },
                }
            },
        }
    )


@pytest.mark.asyncio
async def test_open_session_materializes_config_and_starts_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fabric_config = object()
    translation_calls: list[AgentConfig] = []

    def translate(config: AgentConfig) -> Any:
        translation_calls.append(config)
        return fabric_config

    monkeypatch.setattr(session_manager, "translate_agent_config", translate)
    runtime = _FakeRuntime()
    fabric = _FakeFabric(runtime)
    registry = FabricSessionRegistry()
    agent_config = _agent_config()
    manager = FabricSessionManager(
        agent_config,
        base_dir=tmp_path,
        session_registry=registry,
        fabric=fabric,
    )

    assert translation_calls == []
    assert fabric.start_calls == []

    session = await manager.open_session()

    assert translation_calls == [agent_config]
    assert fabric.start_calls == [(fabric_config, tmp_path)]
    assert session.runtime is runtime
    assert await registry.get(session.session_id) is session


@pytest.mark.asyncio
async def test_open_session_stops_runtime_when_registration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "translate_agent_config", lambda config: object())
    runtime = _FakeRuntime()
    fabric = _FakeFabric(runtime)
    registry = FabricSessionRegistry()

    async def fail_registration(runtime: Any) -> None:
        raise RuntimeError("registration failed")

    monkeypatch.setattr(registry, "register", fail_registration)
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        fabric=fabric,
    )

    with pytest.raises(RuntimeError, match="registration failed"):
        await manager.open_session()

    assert runtime.stop_calls == 1
    assert await registry.count() == 0


@pytest.mark.asyncio
async def test_resolve_session_opens_session_when_id_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_manager, "translate_agent_config", lambda config: object())
    runtime = _FakeRuntime()
    fabric = _FakeFabric(runtime)
    registry = FabricSessionRegistry()
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        fabric=fabric,
    )

    session = await manager.resolve_session(None)

    assert session.runtime is runtime
    assert len(fabric.start_calls) == 1


@pytest.mark.asyncio
async def test_resolve_session_reuses_registered_runtime(
    tmp_path: Path,
) -> None:
    runtime = _FakeRuntime()
    fabric = _FakeFabric(_FakeRuntime())
    registry = FabricSessionRegistry()
    registered = await registry.register(cast(Any, runtime), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        fabric=fabric,
    )

    session = await manager.resolve_session("session-1")

    assert session is registered
    assert session.runtime is runtime
    assert fabric.start_calls == []


@pytest.mark.asyncio
async def test_close_session_removes_session_and_stops_runtime(tmp_path: Path) -> None:
    runtime = _FakeRuntime()
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, runtime), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )

    await manager.close_session(session.session_id)

    assert runtime.stop_calls == 1
    assert await registry.count() == 0
    with pytest.raises(FabricSessionNotFoundError, match="session-1"):
        await manager.resolve_session(session.session_id)


@pytest.mark.asyncio
async def test_close_session_waits_for_active_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _FakeRuntime()
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, runtime), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )
    invocation_started = asyncio.Event()
    release_invocation = asyncio.Event()

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        invocation_started.set()
        await release_invocation.wait()
        return FabricRuntimeResult(status="succeeded", response=request.input)

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)
    invocation = asyncio.create_task(
        manager.invoke_session(session, FabricInvocationRequest(input="hello")),
    )
    await invocation_started.wait()

    close = asyncio.create_task(manager.close_session(session.session_id))
    await asyncio.sleep(0)

    assert runtime.stop_calls == 0
    with pytest.raises(FabricSessionNotFoundError, match="session-1"):
        await manager.resolve_session(session.session_id)

    release_invocation.set()
    await invocation
    await close

    assert runtime.stop_calls == 1


@pytest.mark.asyncio
async def test_resolved_session_cannot_invoke_after_close_starts(tmp_path: Path) -> None:
    runtime = _FakeRuntime()
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, runtime), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )

    await manager.close_session(session.session_id)

    with pytest.raises(FabricSessionNotFoundError, match="session-1"):
        await manager.invoke_session(session, FabricInvocationRequest(input="hello"))


@pytest.mark.asyncio
async def test_expire_idle_sessions_stops_expired_runtime(
    tmp_path: Path,
) -> None:
    runtime = _FakeRuntime()
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, runtime), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )
    session.last_accessed_at = float("-inf")

    expired_count = await manager.expire_idle_sessions(idle_timeout_seconds=30.0)

    assert expired_count == 1
    assert runtime.stop_calls == 1
    assert await registry.count() == 0


@pytest.mark.asyncio
async def test_close_all_sessions_stops_every_runtime(tmp_path: Path) -> None:
    first_runtime = _FakeRuntime()
    second_runtime = _FakeRuntime()
    registry = FabricSessionRegistry()
    await registry.register(cast(Any, first_runtime), session_id="session-1")
    await registry.register(cast(Any, second_runtime), session_id="session-2")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )

    closed_count = await manager.close_all_sessions()

    assert closed_count == 2
    assert first_runtime.stop_calls == 1
    assert second_runtime.stop_calls == 1
    assert await registry.count() == 0


@pytest.mark.asyncio
async def test_close_all_sessions_continues_after_stop_failure(tmp_path: Path) -> None:
    class _FailingRuntime(_FakeRuntime):
        async def stop(self) -> None:
            self.stop_calls += 1
            raise session_manager.FabricError("stop failed")

    failing_runtime = _FailingRuntime()
    healthy_runtime = _FakeRuntime()
    registry = FabricSessionRegistry()
    await registry.register(cast(Any, failing_runtime), session_id="session-1")
    await registry.register(cast(Any, healthy_runtime), session_id="session-2")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )

    closed_count = await manager.close_all_sessions()

    assert closed_count == 2
    assert failing_runtime.stop_calls == 1
    assert healthy_runtime.stop_calls == 1


@pytest.mark.asyncio
async def test_invoke_session_refreshes_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
    )
    refresh_calls: list[Any] = []

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        return FabricRuntimeResult(status="succeeded", response=request.input)

    async def refresh_activity(resolved_session: Any) -> None:
        refresh_calls.append(resolved_session)

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)
    monkeypatch.setattr(registry, "refresh_activity", refresh_activity)

    await manager.invoke_session(session, FabricInvocationRequest(input="hello"))

    assert refresh_calls == [session]


@pytest.mark.asyncio
async def test_invoke_session_serializes_turns_for_same_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        fabric=_FakeFabric(_FakeRuntime()),
    )
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    invocation_order: list[str] = []
    active_invocations = 0
    max_active_invocations = 0

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        nonlocal active_invocations, max_active_invocations
        active_invocations += 1
        max_active_invocations = max(max_active_invocations, active_invocations)
        invocation_order.append(request.input)
        if request.input == "first":
            first_started.set()
            await release_first.wait()
        active_invocations -= 1
        return FabricRuntimeResult(status="succeeded", response=request.input)

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)

    first = asyncio.create_task(
        manager.invoke_session(session, FabricInvocationRequest(input="first")),
    )
    await first_started.wait()
    second = asyncio.create_task(
        manager.invoke_session(session, FabricInvocationRequest(input="second")),
    )
    await asyncio.sleep(0)

    assert invocation_order == ["first"]

    release_first.set()
    results = await asyncio.gather(first, second)

    assert invocation_order == ["first", "second"]
    assert max_active_invocations == 1
    assert [result.response for result in results] == ["first", "second"]


@pytest.mark.asyncio
async def test_invoke_session_releases_lock_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        fabric=_FakeFabric(_FakeRuntime()),
    )
    invocation_count = 0

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        nonlocal invocation_count
        invocation_count += 1
        if invocation_count == 1:
            raise RuntimeError("invoke failed")
        return FabricRuntimeResult(status="succeeded", response="recovered")

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)

    with pytest.raises(RuntimeError, match="invoke failed"):
        await manager.invoke_session(session, FabricInvocationRequest(input="first"))

    result = await manager.invoke_session(session, FabricInvocationRequest(input="second"))

    assert result.response == "recovered"


@pytest.mark.asyncio
async def test_invoke_session_releases_lock_after_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        fabric=_FakeFabric(_FakeRuntime()),
    )
    invocation_started = asyncio.Event()

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        if request.input == "cancel":
            invocation_started.set()
            await asyncio.Event().wait()
        return FabricRuntimeResult(status="succeeded", response="recovered")

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)
    cancelled = asyncio.create_task(
        manager.invoke_session(session, FabricInvocationRequest(input="cancel")),
    )
    await invocation_started.wait()

    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    result = await manager.invoke_session(session, FabricInvocationRequest(input="next"))

    assert result.response == "recovered"


def test_rejects_negative_concurrency_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be greater than or equal to zero"):
        FabricSessionManager(
            _agent_config(),
            base_dir=tmp_path,
            session_registry=FabricSessionRegistry(),
            max_concurrent_invocations=-1,
        )


@pytest.mark.asyncio
async def test_invoke_session_limits_concurrency_across_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    first_session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    second_session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-2")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        max_concurrent_invocations=1,
    )
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    invocation_order: list[str] = []

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        invocation_order.append(request.input)
        if request.input == "first":
            first_started.set()
            await release_first.wait()
        return FabricRuntimeResult(status="succeeded", response=request.input)

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)
    first = asyncio.create_task(
        manager.invoke_session(first_session, FabricInvocationRequest(input="first")),
    )
    await first_started.wait()
    second = asyncio.create_task(
        manager.invoke_session(second_session, FabricInvocationRequest(input="second")),
    )
    await asyncio.sleep(0)

    assert invocation_order == ["first"]

    release_first.set()
    await asyncio.gather(first, second)

    assert invocation_order == ["first", "second"]


@pytest.mark.asyncio
async def test_cancelled_capacity_waiter_does_not_leak_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    first_session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    second_session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-2")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        max_concurrent_invocations=1,
    )
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    invocation_order: list[str] = []

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        invocation_order.append(request.input)
        if request.input == "first":
            first_started.set()
            await release_first.wait()
        return FabricRuntimeResult(status="succeeded", response=request.input)

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)
    first = asyncio.create_task(
        manager.invoke_session(first_session, FabricInvocationRequest(input="first")),
    )
    await first_started.wait()
    cancelled = asyncio.create_task(
        manager.invoke_session(second_session, FabricInvocationRequest(input="cancelled")),
    )
    await asyncio.sleep(0)

    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    release_first.set()
    await first
    result = await manager.invoke_session(second_session, FabricInvocationRequest(input="next"))

    assert invocation_order == ["first", "next"]
    assert result.response == "next"


@pytest.mark.asyncio
async def test_zero_concurrency_limit_allows_parallel_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FabricSessionRegistry()
    first_session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-1")
    second_session = await registry.register(cast(Any, _FakeRuntime()), session_id="session-2")
    manager = FabricSessionManager(
        _agent_config(),
        base_dir=tmp_path,
        session_registry=registry,
        max_concurrent_invocations=0,
    )
    both_started = asyncio.Event()
    release = asyncio.Event()
    active_invocations = 0

    async def invoke_fabric_runtime(runtime: Any, request: FabricInvocationRequest) -> FabricRuntimeResult:
        nonlocal active_invocations
        active_invocations += 1
        if active_invocations == 2:
            both_started.set()
        await release.wait()
        active_invocations -= 1
        return FabricRuntimeResult(status="succeeded", response=request.input)

    monkeypatch.setattr(session_manager, "invoke_fabric_runtime", invoke_fabric_runtime)
    first = asyncio.create_task(
        manager.invoke_session(first_session, FabricInvocationRequest(input="first")),
    )
    second = asyncio.create_task(
        manager.invoke_session(second_session, FabricInvocationRequest(input="second")),
    )

    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()
    await asyncio.gather(first, second)
