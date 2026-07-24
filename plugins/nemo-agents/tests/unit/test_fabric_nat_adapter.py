# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Platform-owned NAT Fabric adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from nemo_agents_plugin.agent_config import load_agent_config
from nemo_agents_plugin.fabric.adapters.nat import adapter as nat_adapter
from nemo_agents_plugin.fabric.translator import translate_agent_config
from nemo_fabric_adapters.common import lifecycle  # ty: ignore[unresolved-import]


class _FakeRunner:
    def __init__(self, result: Any = "done", error: Exception | None = None) -> None:
        self.result_value = result
        self.error = error

    async def __aenter__(self) -> _FakeRunner:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    async def result(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.result_value


class _FakeSession:
    def __init__(self, sessions: _FakeSessions) -> None:
        self.sessions = sessions

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def run(self, value: Any, *, runtime_type: Any) -> _FakeRunner:
        self.sessions.run_calls.append({"input": value, "runtime_type": runtime_type})
        return self.sessions.runner


class _FakeSessions:
    def __init__(self, runner: _FakeRunner | None = None) -> None:
        self.runner = runner or _FakeRunner()
        self.session_calls: list[dict[str, str]] = []
        self.run_calls: list[dict[str, Any]] = []

    def session(self, **kwargs: str) -> _FakeSession:
        self.session_calls.append(kwargs)
        return _FakeSession(self)


class _FakeWorkflowContext:
    def __init__(self, sessions: _FakeSessions, enter_error: Exception | None = None) -> None:
        self.sessions = sessions
        self.enter_error = enter_error
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> _FakeSessions:
        self.entered = True
        if self.enter_error is not None:
            raise self.enter_error
        return self.sessions

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.exited = True


def _start_payload(
    *,
    settings: dict[str, Any] | None = None,
    models: dict[str, Any] | None = None,
    runtime_id: str = "runtime-1",
) -> dict[str, Any]:
    return {
        "base_dir": "/tmp/agent",
        "config": {
            "harness": {
                "settings": settings or {"workflow": "current_timezone"},
            },
            "models": models or {},
        },
        "runtime_context": {
            "runtime_id": runtime_id,
        },
    }


def _react_payload(
    *,
    tools: list[str],
    provider: str = "nvidia",
    model_settings: dict[str, Any] | None = None,
    instructions: str | None = None,
) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "workflow": "react",
        "tools": tools,
    }
    if instructions is not None:
        settings["instructions"] = instructions
    return _start_payload(
        settings=settings,
        models={
            "default": {
                "provider": provider,
                "model": "platform-model",
                "api_key_env": "NVIDIA_API_KEY",
                "temperature": 0.1,
                "settings": model_settings or {},
            }
        },
    )


def _invoke_payload(*, runtime_id: str = "runtime-1") -> dict[str, Any]:
    return {
        "runtime_context": {
            "runtime_id": runtime_id,
        },
        "request": {
            "input": "hello",
            "request_id": "request-1",
            "context": {
                "user_id": "user-1",
                "conversation_id": "conversation-1",
            },
        },
    }


@pytest.mark.asyncio
async def test_runtime_owns_nat_workflow_across_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = _FakeSessions(runner=_FakeRunner(result={"answer": "hello"}))
    workflow = _FakeWorkflowContext(sessions)
    monkeypatch.setattr(nat_adapter, "load_nat_workflow", lambda payload: workflow)
    runtime = nat_adapter.NatRuntime()

    await runtime.start(_start_payload())
    output = await runtime.invoke(_invoke_payload())
    await runtime.stop()

    from nat.data_models.runtime_enum import RuntimeTypeEnum

    assert workflow.entered is True
    assert workflow.exited is True
    assert sessions.session_calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "user_message_id": "request-1",
        }
    ]
    assert sessions.run_calls == [
        {
            "input": "hello",
            "runtime_type": RuntimeTypeEnum.RUN_OR_SERVE,
        }
    ]
    assert output == {
        "harness": "nat",
        "adapter": "python",
        "mode": "nat_workflow",
        "response": {"answer": "hello"},
        "completed": True,
        "failed": False,
        "error": None,
    }


@pytest.mark.asyncio
async def test_invoke_failure_is_normalized_without_exception_details(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = _FakeSessions(runner=_FakeRunner(error=RuntimeError("credential secret")))
    workflow = _FakeWorkflowContext(sessions)
    monkeypatch.setattr(nat_adapter, "load_nat_workflow", lambda payload: workflow)
    runtime = nat_adapter.NatRuntime()

    await runtime.start(_start_payload())
    output = await runtime.invoke(_invoke_payload())
    await runtime.stop()

    assert output["failed"] is True
    assert output["response"] is None
    assert output["error"] == {
        "code": "nat_workflow_invoke_failed",
        "message": "NAT workflow invocation failed; inspect adapter stderr for details",
        "retryable": False,
    }
    assert "credential secret" not in str(output)


@pytest.mark.asyncio
async def test_start_failure_is_actionable_and_stop_remains_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions(), enter_error=RuntimeError("invalid workflow"))
    monkeypatch.setattr(nat_adapter, "load_nat_workflow", lambda payload: workflow)
    runtime = nat_adapter.NatRuntime()

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await runtime.start(_start_payload())

    assert error_info.value.code == "nat_workflow_start_failed"
    assert "invalid workflow" not in error_info.value.message
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_rejects_second_start(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions())
    monkeypatch.setattr(nat_adapter, "load_nat_workflow", lambda payload: workflow)
    runtime = nat_adapter.NatRuntime()
    await runtime.start(_start_payload())

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await runtime.start(_start_payload())

    assert error_info.value.code == "nat_runtime_already_started"
    await runtime.stop()


@pytest.mark.asyncio
async def test_unsupported_normalized_fabric_fields_are_rejected() -> None:
    payload = _start_payload()
    payload["config"]["telemetry"] = {"providers": {"custom": {"enabled": True}}}

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await nat_adapter.NatRuntime().start(payload)

    assert error_info.value.code == "nat_unsupported_fabric_config"
    assert error_info.value.metadata == {"fields": ["telemetry"]}


def test_calculator_config_is_built_from_fabric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-value")
    payload = _react_payload(
        tools=["calculator", "current_datetime"],
        model_settings={
            "base_url": "https://platform.example/v1",
            "max_tokens": 777,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )

    config = nat_adapter.build_nat_config(payload)

    assert set(config.function_groups) == {"calculator"}
    assert set(config.functions) == {"current_datetime"}
    assert config.workflow.tool_names == ["calculator", "current_datetime"]
    assert config.workflow.llm_name == "default"
    assert config.workflow.use_native_tool_calling is True
    llm = config.llms["default"]
    assert llm.model_name == "platform-model"
    assert llm.api_key.get_secret_value() == "secret-value"
    assert llm.temperature == 0.1
    assert llm.base_url == "https://platform.example/v1"
    assert llm.max_tokens == 777
    assert llm.chat_template_kwargs == {"enable_thinking": False}


def test_phishing_config_is_built_from_fabric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-value")
    payload = _react_payload(
        tools=["email_phishing_analyzer"],
        provider="openai",
        model_settings={
            "base_url": "https://integrate.api.nvidia.com/v1",
            "max_tokens": 1024,
        },
        instructions='Classify the email as "phishing" or "benign".',
    )

    config = nat_adapter.build_nat_config(payload)

    assert set(config.functions) == {"email_phishing_analyzer"}
    assert config.functions["email_phishing_analyzer"].llm == "default"
    assert config.workflow.tool_names == ["email_phishing_analyzer"]
    assert config.workflow.additional_instructions == 'Classify the email as "phishing" or "benign".'
    assert config.llms["default"].base_url == "https://integrate.api.nvidia.com/v1"


@pytest.mark.parametrize(
    ("example_name", "expected_tools"),
    [
        ("nat-calculator", ["calculator", "current_datetime"]),
        ("nat-email-phishing", ["email_phishing_analyzer"]),
    ],
)
def test_repository_agent_yaml_builds_typed_nat_config(
    example_name: str,
    expected_tools: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    example_path = Path(__file__).parents[2] / "examples/nemo-agent-config" / example_name / "agent.yaml"
    agent_config = load_agent_config(example_path)
    fabric_config = translate_agent_config(agent_config)
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-value")

    nat_config = nat_adapter.build_nat_config({"config": fabric_config.to_mapping()})

    assert nat_config.workflow.tool_names == expected_tools
    assert set(nat_config.llms) == {"default"}


def test_native_nat_config_fields_are_rejected() -> None:
    payload = _start_payload(settings={"config_file": "./workflow.yml"})

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        nat_adapter.build_nat_config(payload)

    assert error_info.value.code == "nat_invalid_harness_settings"


def test_current_timezone_rejects_fabric_models() -> None:
    payload = _start_payload(
        models={
            "default": {
                "provider": "nvidia",
                "model": "unused",
            }
        }
    )

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        nat_adapter.build_nat_config(payload)

    assert error_info.value.code == "nat_invalid_models"


def test_fabric_model_requires_configured_api_key_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _react_payload(tools=["calculator"])
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        nat_adapter.build_nat_config(payload)

    assert error_info.value.code == "nat_model_api_key_missing"
    assert error_info.value.metadata == {
        "llm": "default",
        "api_key_env": "NVIDIA_API_KEY",
    }


def test_fabric_model_settings_cannot_replace_nat_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _react_payload(
        tools=["calculator"],
        model_settings={
            "_type": "openai",
            "model_name": "settings-model",
        },
    )
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-value")

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        nat_adapter.build_nat_config(payload)

    assert error_info.value.code == "nat_model_settings_reserved"
    assert error_info.value.metadata == {
        "llm": "default",
        "fields": ["_type", "model_name"],
    }


def test_unsupported_fabric_model_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _react_payload(tools=["calculator"], provider="anthropic")
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-value")

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        nat_adapter.build_nat_config(payload)

    assert error_info.value.code == "nat_model_provider_unsupported"
    assert error_info.value.metadata == {"provider": "anthropic"}


def test_native_mcp_server_is_added_to_workflow_tools() -> None:
    config = SimpleNamespace(
        workflow=SimpleNamespace(tool_names=["current_datetime"]),
        functions={},
        function_groups={},
    )
    payload = {
        "capability_plan": {
            "native": {
                "mcp_servers": {
                    "repo": {
                        "transport": "stdio",
                        "url": "repo-mcp --root .",
                        "exposure": "harness_native",
                    }
                }
            }
        }
    }

    nat_adapter.apply_nat_capabilities(config, payload)

    mcp_group = config.function_groups["repo"]
    assert config.workflow.tool_names == ["current_datetime", "repo"]
    assert mcp_group.server.transport == "stdio"
    assert mcp_group.server.command == "repo-mcp"
    assert mcp_group.server.args == ["--root", "."]


def test_blocked_tools_remove_functions_and_filter_group_members() -> None:
    calculator = SimpleNamespace(include=[], exclude=[])
    config = SimpleNamespace(
        workflow=SimpleNamespace(tool_names=["current_datetime", "calculator"]),
        functions={"current_datetime": object()},
        function_groups={"calculator": calculator},
    )
    payload = {
        "config": {
            "tools": {
                "blocked": ["current_datetime", "calculator__divide"],
            }
        }
    }

    nat_adapter.apply_nat_capabilities(config, payload)

    assert config.workflow.tool_names == ["calculator"]
    assert config.functions == {}
    assert calculator.exclude == ["divide"]


@pytest.mark.asyncio
async def test_skill_paths_remain_explicitly_unsupported() -> None:
    payload = _start_payload()
    payload["config"]["skills"] = {"paths": ["./skills/review"]}
    payload["capability_plan"] = {
        "unsupported": {
            "skill_paths": ["/tmp/agent/skills/review"],
        }
    }

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await nat_adapter.NatRuntime().start(payload)

    assert error_info.value.code == "nat_unsupported_fabric_config"
    assert error_info.value.metadata == {"fields": ["skills"]}


@pytest.mark.asyncio
async def test_fabric_managed_mcp_remains_explicitly_unsupported() -> None:
    payload = _start_payload()
    payload["config"]["mcp"] = {
        "servers": {
            "repo": {
                "transport": "streamable-http",
                "url": "http://localhost:9901/mcp",
                "exposure": "fabric_managed",
            }
        }
    }
    payload["capability_plan"] = {
        "unsupported": {
            "mcp_servers": payload["config"]["mcp"]["servers"],
        }
    }

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await nat_adapter.NatRuntime().start(payload)

    assert error_info.value.code == "nat_unsupported_fabric_config"
    assert error_info.value.metadata == {"fields": ["mcp"]}


@pytest.mark.asyncio
async def test_runtime_rejects_mismatched_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions())
    monkeypatch.setattr(nat_adapter, "load_nat_workflow", lambda payload: workflow)
    runtime = nat_adapter.NatRuntime()
    await runtime.start(_start_payload())

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await runtime.invoke(_invoke_payload(runtime_id="runtime-2"))

    assert error_info.value.code == "nat_runtime_mismatch"
    await runtime.stop()


@pytest.mark.asyncio
async def test_stop_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions())
    monkeypatch.setattr(nat_adapter, "load_nat_workflow", lambda payload: workflow)
    runtime = nat_adapter.NatRuntime()
    await runtime.start(_start_payload())

    await runtime.stop()
    await runtime.stop()

    assert workflow.exited is True
