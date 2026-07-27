# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from nemo_agents_plugin.agent_config import AgentConfig, AgentConfigLoadError
from nemo_agents_plugin.fabric import server
from nemo_agents_plugin.fabric.runtime import (
    FabricRuntimeExecutionError,
    FabricRuntimeResult,
    FabricRuntimeTimeoutError,
)
from nemo_agents_plugin.fabric.server import SESSION_ID_HEADER, create_fabric_serving_app
from nemo_agents_plugin.fabric.serving_models import ChatCompletionRequest
from nemo_agents_plugin.fabric.session_manager import FabricSessionManager, FabricSessionStartError
from nemo_agents_plugin.fabric.session_registry import FabricSessionNotFoundError, FabricSessionRegistry


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
        assert isinstance(app.state.session_manager, FabricSessionManager)

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


def test_chat_completion_without_session_id_opens_and_returns_session(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_agent_config(tmp_path)
    app = create_fabric_serving_app(config_path)
    resolve_calls: list[str | None] = []
    invocation_calls: list[tuple[Any, Any]] = []
    runtime = object()

    async def resolve_session(session_id: str | None) -> Any:
        resolve_calls.append(session_id)
        return SimpleNamespace(session_id="session-1", runtime=runtime)

    async def invoke_fabric_runtime(active_runtime: Any, request: Any) -> FabricRuntimeResult:
        invocation_calls.append((active_runtime, request))
        return FabricRuntimeResult(
            status="succeeded",
            output={"response": "hello", "usage": {"total_tokens": 3}},
            response="hello",
            invocation_id="invocation-1",
        )

    monkeypatch.setattr(server, "invoke_fabric_runtime", invoke_fabric_runtime)

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert response.json() == {
        "id": "invocation-1",
        "object": "chat.completion",
        "model": "unknown-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 3},
    }
    assert resolve_calls == [None]
    active_runtime, invocation_request = invocation_calls[0]
    assert active_runtime is runtime
    assert invocation_request.input == "hello"
    assert invocation_request.caller_context == {"session_id": "session-1"}


def test_chat_completion_with_session_id_reuses_session(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_agent_config(tmp_path)
    app = create_fabric_serving_app(config_path)
    resolve_calls: list[str | None] = []

    async def resolve_session(session_id: str | None) -> Any:
        resolve_calls.append(session_id)
        return SimpleNamespace(session_id="session-1", runtime=object())

    async def invoke_fabric_runtime(active_runtime: Any, request: Any) -> FabricRuntimeResult:
        return FabricRuntimeResult(status="succeeded", response="hello again")

    monkeypatch.setattr(server, "invoke_fabric_runtime", invoke_fabric_runtime)

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        response = client.post(
            "/v1/chat/completions",
            headers={SESSION_ID_HEADER: "session-1"},
            json={"messages": [{"role": "user", "content": "hello again"}]},
        )

    assert response.status_code == 200
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert resolve_calls == ["session-1"]


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (FabricRuntimeTimeoutError("timed out"), 504),
        (FabricRuntimeExecutionError("invoke failed"), 502),
    ],
)
def test_chat_completion_maps_runtime_errors(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    async def resolve_session(session_id: str | None) -> Any:
        return SimpleNamespace(session_id="session-1", runtime=object())

    async def invoke_fabric_runtime(active_runtime: Any, request: Any) -> FabricRuntimeResult:
        raise error

    monkeypatch.setattr(server, "invoke_fabric_runtime", invoke_fabric_runtime)

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == status_code
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert response.json() == {"detail": str(error)}


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (FabricSessionNotFoundError("missing session"), 404),
        (FabricSessionStartError("startup failed"), 503),
    ],
)
def test_chat_completion_maps_session_resolution_errors(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    async def resolve_session(session_id: str | None) -> Any:
        raise error

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        response = client.post(
            "/v1/chat/completions",
            headers={SESSION_ID_HEADER: "missing"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == status_code
    assert SESSION_ID_HEADER not in response.headers
    assert response.json() == {"detail": str(error)}


def test_chat_completion_maps_failed_run_result(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    async def resolve_session(session_id: str | None) -> Any:
        return SimpleNamespace(session_id="session-1", runtime=object())

    async def invoke_fabric_runtime(active_runtime: Any, request: Any) -> FabricRuntimeResult:
        return FabricRuntimeResult(
            status="failed",
            error={"stage": "invoke", "message": "adapter failed"},
        )

    monkeypatch.setattr(server, "invoke_fabric_runtime", invoke_fabric_runtime)

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 502
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert response.json() == {"detail": "adapter failed"}


def test_chat_completion_request_translates_final_user_turn() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "assistant", "content": "How can I help?"},
                {"role": "user", "content": "Say hello."},
            ],
            "model": "test-model",
            "stream": False,
        }
    )

    invocation_request = server._to_fabric_invocation_request(request, session_id="session-1")

    assert invocation_request.input == "Say hello."
    assert invocation_request.caller_context == {"session_id": "session-1"}
