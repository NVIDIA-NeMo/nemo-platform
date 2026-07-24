# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Platform-owned NAT Fabric adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from nemo_agents_plugin.fabric.adapters.nat import adapter as nat_adapter
from nemo_fabric_adapters.common import lifecycle  # ty: ignore[unresolved-import]


class _FakeRunner:
    def __init__(self, result: Any = "done", error: Exception | None = None) -> None:
        self.result_value = result
        self.error = error

    async def __aenter__(self) -> "_FakeRunner":
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
    def __init__(self, sessions: "_FakeSessions") -> None:
        self.sessions = sessions

    async def __aenter__(self) -> "_FakeSession":
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


def _start_payload(base_dir: Path, *, runtime_id: str = "runtime-1") -> dict[str, Any]:
    return {
        "base_dir": str(base_dir),
        "config": {
            "harness": {
                "settings": {
                    "config_file": "./workflow.yml",
                }
            }
        },
        "runtime_context": {
            "runtime_id": runtime_id,
        },
    }


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


@pytest.fixture()
def nat_config(tmp_path: Path) -> Path:
    config = tmp_path / "workflow.yml"
    config.write_text("workflow:\n  _type: current_timezone\n", encoding="utf-8")
    return config


@pytest.mark.asyncio
async def test_runtime_owns_nat_workflow_across_invoke(
    nat_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _FakeSessions(runner=_FakeRunner(result={"answer": "hello"}))
    workflow = _FakeWorkflowContext(sessions)
    monkeypatch.setattr("nat.runtime.loader.load_workflow", lambda path: workflow)
    runtime = nat_adapter.NatRuntime()

    await runtime.start(_start_payload(nat_config.parent))
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
async def test_invoke_failure_is_normalized_without_exception_details(
    nat_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _FakeSessions(runner=_FakeRunner(error=RuntimeError("credential secret")))
    workflow = _FakeWorkflowContext(sessions)
    monkeypatch.setattr("nat.runtime.loader.load_workflow", lambda path: workflow)
    runtime = nat_adapter.NatRuntime()

    await runtime.start(_start_payload(nat_config.parent))
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
async def test_start_failure_is_actionable_and_stop_remains_safe(
    nat_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions(), enter_error=RuntimeError("invalid workflow"))
    monkeypatch.setattr("nat.runtime.loader.load_workflow", lambda path: workflow)
    runtime = nat_adapter.NatRuntime()

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await runtime.start(_start_payload(nat_config.parent))

    assert error_info.value.code == "nat_workflow_start_failed"
    assert "invalid workflow" not in error_info.value.message
    await runtime.stop()


@pytest.mark.asyncio
async def test_config_file_must_stay_within_agent_directory(tmp_path: Path) -> None:
    base_dir = tmp_path / "agent"
    base_dir.mkdir()
    outside = tmp_path / "workflow.yml"
    outside.write_text("workflow: {}\n", encoding="utf-8")
    payload = _start_payload(base_dir)
    payload["config"]["harness"]["settings"]["config_file"] = str(outside)

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await nat_adapter.NatRuntime().start(payload)

    assert error_info.value.code == "nat_config_file_outside_base_dir"


@pytest.mark.asyncio
async def test_normalized_fabric_fields_are_rejected(nat_config: Path) -> None:
    payload = _start_payload(nat_config.parent)
    payload["config"]["models"] = {
        "default": {
            "provider": "nvidia",
            "model": "example-model",
        }
    }

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await nat_adapter.NatRuntime().start(payload)

    assert error_info.value.code == "nat_unsupported_fabric_config"
    assert error_info.value.metadata == {"fields": ["models"]}


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
async def test_skill_paths_remain_explicitly_unsupported(nat_config: Path) -> None:
    payload = _start_payload(nat_config.parent)
    payload["config"]["skills"] = {"paths": ["./skills/review"]}
    payload["capability_plan"] = {
        "unsupported": {
            "skill_paths": [str(nat_config.parent / "skills/review")],
        }
    }

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await nat_adapter.NatRuntime().start(payload)

    assert error_info.value.code == "nat_unsupported_fabric_config"
    assert error_info.value.metadata == {"fields": ["skills"]}


@pytest.mark.asyncio
async def test_fabric_managed_mcp_remains_explicitly_unsupported(nat_config: Path) -> None:
    payload = _start_payload(nat_config.parent)
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
async def test_runtime_rejects_mismatched_invocation(
    nat_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions())
    monkeypatch.setattr("nat.runtime.loader.load_workflow", lambda path: workflow)
    runtime = nat_adapter.NatRuntime()
    await runtime.start(_start_payload(nat_config.parent))

    with pytest.raises(lifecycle.LifecycleError) as error_info:
        await runtime.invoke(_invoke_payload(runtime_id="runtime-2"))

    assert error_info.value.code == "nat_runtime_mismatch"
    await runtime.stop()


@pytest.mark.asyncio
async def test_stop_is_idempotent(
    nat_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _FakeWorkflowContext(_FakeSessions())
    monkeypatch.setattr("nat.runtime.loader.load_workflow", lambda path: workflow)
    runtime = nat_adapter.NatRuntime()
    await runtime.start(_start_payload(nat_config.parent))

    await runtime.stop()
    await runtime.stop()

    assert workflow.exited is True
