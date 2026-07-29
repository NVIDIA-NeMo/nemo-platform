# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
from nemo_agents_plugin.fabric.server import SESSION_ID_HEADER, FabricServingSettings, create_fabric_serving_app
from nemo_agents_plugin.fabric.serving_models import ChatCompletionRequest
from nemo_agents_plugin.fabric.session_manager import (
    FabricSessionManager,
    FabricSessionStartError,
    FabricSessionStopError,
)
from nemo_agents_plugin.fabric.session_registry import FabricSessionNotFoundError, FabricSessionRegistry


class _FakeStreamContext:
    def __init__(self, stream: Any = None, enter_error: BaseException | None = None) -> None:
        self.stream = stream
        self.enter_error = enter_error
        self.exit_calls = 0

    async def __aenter__(self) -> Any:
        if self.enter_error is not None:
            raise self.enter_error
        return self.stream

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exit_calls += 1


class _FakeFabricStream:
    def __init__(
        self,
        records: list[dict[str, Any]] | None = None,
        *,
        result: FabricRuntimeResult | None = None,
    ) -> None:
        self._records = records or []
        self._result = result or FabricRuntimeResult(status="succeeded", response="done")
        self.aclose_calls = 0

    async def records(self) -> Any:
        for record in self._records:
            yield record

    async def result(self) -> FabricRuntimeResult:
        return self._result

    async def aclose(self) -> None:
        self.aclose_calls += 1


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


def _sse_payload(event: str) -> dict[str, object]:
    assert event.startswith("data: ")
    assert event.endswith("\n\n")
    return json.loads(event.removeprefix("data: ").removesuffix("\n\n"))


def _sse_line_payload(line: str) -> dict[str, object]:
    assert line.startswith("data: ")
    return json.loads(line.removeprefix("data: "))


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


def test_shutdown_stops_all_registered_runtimes(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
) -> None:
    class _Runtime:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def stop(self) -> None:
            self.stop_calls += 1

    runtime = _Runtime()
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    with TestClient(app) as client:
        registry = app.state.session_registry

        async def register_runtime() -> None:
            await registry.register(cast(Any, runtime), session_id="session-1")

        client.portal.call(register_runtime)

    assert runtime.stop_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_error", [RuntimeError("cleanup failed"), asyncio.CancelledError()])
async def test_shutdown_stops_sessions_when_cleanup_task_fails(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
    cleanup_error: BaseException,
) -> None:
    close_calls = 0

    async def fail_cleanup(*args: Any, **kwargs: Any) -> None:
        raise cleanup_error

    async def close_all_sessions(self: FabricSessionManager) -> int:
        nonlocal close_calls
        close_calls += 1
        return 0

    monkeypatch.setattr(server, "_run_idle_session_cleanup", fail_cleanup)
    monkeypatch.setattr(FabricSessionManager, "close_all_sessions", close_all_sessions)
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    with pytest.raises(type(cleanup_error)):
        async with app.router.lifespan_context(app):
            pass

    assert close_calls == 1


def test_startup_fails_for_invalid_agent_config(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
) -> None:
    config_path = _write_agent_config(tmp_path, {"name": "invalid"})
    app = create_fabric_serving_app(config_path)

    with pytest.raises(AgentConfigLoadError), TestClient(app):
        pass

    assert mock_validate_agent_config == []


def test_rejects_invalid_serving_settings() -> None:
    with pytest.raises(ValueError, match="max_concurrent_invocations"):
        FabricServingSettings(max_concurrent_invocations=-1)
    with pytest.raises(ValueError, match="idle_session_timeout_seconds"):
        FabricServingSettings(idle_session_timeout_seconds=0)
    with pytest.raises(ValueError, match="session_cleanup_interval_seconds"):
        FabricServingSettings(session_cleanup_interval_seconds=0)


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

    async def invoke_session(session: Any, request: Any) -> FabricRuntimeResult:
        invocation_calls.append((session, request))
        return FabricRuntimeResult(
            status="succeeded",
            output={"response": "hello", "usage": {"total_tokens": 3}},
            response="hello",
            invocation_id="invocation-1",
        )

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "invoke_session", invoke_session)
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
    resolved_session, invocation_request = invocation_calls[0]
    assert resolved_session.runtime is runtime
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

    async def invoke_session(session: Any, request: Any) -> FabricRuntimeResult:
        return FabricRuntimeResult(status="succeeded", response="hello again")

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "invoke_session", invoke_session)
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

    async def invoke_session(session: Any, request: Any) -> FabricRuntimeResult:
        raise error

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "invoke_session", invoke_session)
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


def test_streaming_chat_completion_maps_stream_start_errors(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    async def resolve_session(session_id: str | None) -> Any:
        return SimpleNamespace(session_id="session-1", runtime=object())

    def stream_session(session: Any, request: Any) -> _FakeStreamContext:
        return _FakeStreamContext(enter_error=FabricRuntimeExecutionError("stream failed"))

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "stream_session", stream_session)
        response = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
        )

    assert response.status_code == 502
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert response.json() == {"detail": "stream failed"}


def test_streaming_chat_completion_returns_openai_sse_response(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))
    resolve_calls: list[str | None] = []
    stream_calls: list[tuple[Any, Any]] = []
    runtime = object()
    fabric_stream = _FakeFabricStream(
        [
            {"kind": "scope", "scope_category": "start", "name": "request"},
            {"data": {"choices": [{"delta": {"content": "hel"}}]}},
            {"data": {"type": "agentMessage", "phase": "final_answer", "text": "lo"}},
        ],
        result=FabricRuntimeResult(status="succeeded", response="hello"),
    )
    stream_context = _FakeStreamContext(fabric_stream)

    async def resolve_session(session_id: str | None) -> Any:
        resolve_calls.append(session_id)
        return SimpleNamespace(session_id="session-1", runtime=runtime)

    def stream_session(session: Any, request: Any) -> _FakeStreamContext:
        stream_calls.append((session, request))
        return stream_context

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "stream_session", stream_session)
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}], "stream": True, "model": "test-model"},
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert resolve_calls == [None]
    resolved_session, invocation_request = stream_calls[0]
    assert resolved_session.runtime is runtime
    assert invocation_request.input == "hello"
    assert invocation_request.caller_context == {"session_id": "session-1"}
    assert stream_context.exit_calls == 1
    assert fabric_stream.aclose_calls == 0

    assert lines[-1] == "data: [DONE]"
    assert _sse_line_payload(lines[0])["choices"] == [{"index": 0, "delta": {"role": "assistant"}}]
    assert _sse_line_payload(lines[1])["choices"] == [{"index": 0, "delta": {"content": "hel"}}]
    assert _sse_line_payload(lines[2])["choices"] == [{"index": 0, "delta": {"content": "lo"}}]
    assert _sse_line_payload(lines[3])["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]


def test_streaming_chat_completion_reuses_supplied_session_id(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))
    resolve_calls: list[str | None] = []

    async def resolve_session(session_id: str | None) -> Any:
        resolve_calls.append(session_id)
        return SimpleNamespace(session_id="session-1", runtime=object())

    def stream_session(session: Any, request: Any) -> _FakeStreamContext:
        return _FakeStreamContext(_FakeFabricStream(result=FabricRuntimeResult(status="succeeded", response="done")))

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "stream_session", stream_session)
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={SESSION_ID_HEADER: "session-1"},
            json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert response.headers[SESSION_ID_HEADER] == "session-1"
    assert resolve_calls == ["session-1"]
    assert _sse_line_payload(lines[1])["choices"] == [{"index": 0, "delta": {"content": "done"}}]


@pytest.mark.asyncio
async def test_streaming_chat_completion_emits_sse_error_and_closes_stream() -> None:
    fabric_stream = _FakeFabricStream(
        [{"data": {"choices": [{"delta": {"content": "partial"}}]}}],
        result=FabricRuntimeResult(
            status="failed",
            error={"message": "terminal failure"},
        ),
    )
    stream_context = _FakeStreamContext(fabric_stream)

    events = [
        event
        async for event in server._iter_streaming_chat_completion(
            stream_context,
            fabric_stream,
            completion_id="chatcmpl-test",
            model="test-model",
        )
    ]

    assert _sse_payload(events[1])["choices"] == [{"index": 0, "delta": {"content": "partial"}}]
    assert _sse_payload(events[2]) == {
        "error": {
            "message": "terminal failure",
            "type": "FabricStreamResultError",
        }
    }
    assert fabric_stream.aclose_calls == 1
    assert stream_context.exit_calls == 1


@pytest.mark.asyncio
async def test_streaming_chat_completion_closes_stream_on_generator_close() -> None:
    fabric_stream = _FakeFabricStream([{"data": {"choices": [{"delta": {"content": "partial"}}]}}])
    stream_context = _FakeStreamContext(fabric_stream)
    events = server._iter_streaming_chat_completion(
        stream_context,
        fabric_stream,
        completion_id="chatcmpl-test",
        model="test-model",
    )

    assert _sse_payload(await events.__anext__())["choices"] == [{"index": 0, "delta": {"role": "assistant"}}]

    await events.aclose()

    assert fabric_stream.aclose_calls == 1
    assert stream_context.exit_calls == 1


def test_chat_completion_maps_failed_run_result(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    async def resolve_session(session_id: str | None) -> Any:
        return SimpleNamespace(session_id="session-1", runtime=object())

    async def invoke_session(session: Any, request: Any) -> FabricRuntimeResult:
        return FabricRuntimeResult(
            status="failed",
            error={"stage": "invoke", "message": "adapter failed"},
        )

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "resolve_session", resolve_session)
        monkeypatch.setattr(app.state.session_manager, "invoke_session", invoke_session)
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


def test_close_session_stops_registered_runtime(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))
    close_calls: list[str] = []

    async def close_session(session_id: str) -> None:
        close_calls.append(session_id)

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "close_session", close_session)
        response = client.delete("/v1/sessions/session-1")

    assert response.status_code == 204
    assert response.content == b""
    assert close_calls == ["session-1"]


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (FabricSessionNotFoundError("missing session"), 404),
        (FabricSessionStopError("shutdown failed"), 502),
    ],
)
def test_close_session_maps_errors(
    tmp_path: Path,
    mock_validate_agent_config: list[tuple[AgentConfig, Path]],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    app = create_fabric_serving_app(_write_agent_config(tmp_path))

    async def close_session(session_id: str) -> None:
        raise error

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.session_manager, "close_session", close_session)
        response = client.delete("/v1/sessions/session-1")

    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}


@pytest.mark.asyncio
async def test_idle_cleanup_runs_periodically_until_shutdown() -> None:
    cleanup_calls: list[float] = []
    cleanup_ran = asyncio.Event()
    shutdown = asyncio.Event()

    class _Manager:
        async def expire_idle_sessions(self, *, idle_timeout_seconds: float) -> int:
            cleanup_calls.append(idle_timeout_seconds)
            cleanup_ran.set()
            return 0

    cleanup = asyncio.create_task(
        server._run_idle_session_cleanup(
            cast(Any, _Manager()),
            idle_timeout_seconds=30.0,
            cleanup_interval_seconds=0.01,
            shutdown_event=shutdown,
        )
    )
    await asyncio.wait_for(cleanup_ran.wait(), timeout=1)
    shutdown.set()
    await cleanup

    assert cleanup_calls == [30.0]
