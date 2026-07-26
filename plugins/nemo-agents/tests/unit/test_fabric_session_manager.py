# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric import session_manager
from nemo_agents_plugin.fabric.session_manager import FabricSessionManager
from nemo_agents_plugin.fabric.session_registry import FabricSessionRegistry


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
