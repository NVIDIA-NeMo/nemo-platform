# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from nemo_agents_plugin.agent_config import AgentConfig, AgentConfigLoadError
from nemo_agents_plugin.fabric import server
from nemo_agents_plugin.fabric.server import create_fabric_serving_app
from nemo_agents_plugin.fabric.session_registry import FabricSessionRegistry


@pytest.fixture()
def mock_validate_agent_config(monkeypatch: pytest.MonkeyPatch) -> list[tuple[AgentConfig, Path]]:
    validation_calls: list[tuple[AgentConfig, Path]] = []

    async def validate(config: AgentConfig, *, base_dir: Path) -> object:
        validation_calls.append((config, base_dir))
        return object()

    monkeypatch.setattr(server, "_validate_agent_config", validate)
    return validation_calls


def _example_config() -> dict[str, Any]:
    return {
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


def _write_agent_config(tmp_path: Path, config: dict[str, Any] | None = None) -> Path:
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(yaml.safe_dump(config or _example_config()), encoding="utf-8")
    return config_path


def test_startup_loads_and_validates_agent_config(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
) -> None:
    config_path = _write_agent_config(tmp_path)
    app = create_fabric_serving_app(config_path)

    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert app.state.agent_config.name == "test-agent"
        assert app.state.base_dir == tmp_path
        assert app.state.validation_result is not None
        assert isinstance(app.state.session_registry, FabricSessionRegistry)

    assert mock_validate_agent_config == [(app.state.agent_config, tmp_path)]


def test_startup_fails_for_invalid_agent_config(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
) -> None:
    config_path = _write_agent_config(tmp_path, {"name": "invalid"})
    app = create_fabric_serving_app(config_path)

    with pytest.raises(AgentConfigLoadError), TestClient(app):
        pass

    assert mock_validate_agent_config == []


def test_chat_completions_is_unavailable_until_session_manager_is_added(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
) -> None:
    config_path = _write_agent_config(tmp_path)
    app = create_fabric_serving_app(config_path)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Fabric runtime session manager is not initialized."}
