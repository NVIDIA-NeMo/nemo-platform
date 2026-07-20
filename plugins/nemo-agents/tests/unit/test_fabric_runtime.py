# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Fabric runtime execution helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from nemo_agents_plugin.fabric import runtime as fabric_runtime
from nemo_agents_plugin.fabric.runtime import (
    FabricRuntimeExecutionError,
    FabricRuntimeRequest,
    FabricRuntimeTimeoutError,
    normalize_fabric_run_result,
    run_fabric_agent_once,
)
from nemo_fabric import FabricConfig, RunResult  # ty: ignore[unresolved-import]


class _FabricMapping:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping

    def to_mapping(self) -> dict[str, Any]:
        return self._mapping


class _FakeRunResult:
    def __init__(
        self,
        *,
        status: str = "succeeded",
        output: Any | None = None,
        error: Any | None = None,
    ) -> None:
        self.status = status
        self.output = output if output is not None else _FabricMapping({"response": "hello"})
        self.error = error
        self.artifacts = _FabricMapping({"root": "/tmp/artifacts", "artifacts": []})
        self.telemetry = (_FabricMapping({"provider": "relay", "kind": "trace"}),)
        self.events = (_FabricMapping({"kind": "runtime_start", "message": "started"}),)
        self.metadata = {"adapter_runner": "python"}
        self.runtime_id = "runtime-1"
        self.invocation_id = "invocation-1"
        self.request_id = "request-1"


class _FakeRuntime:
    def __init__(
        self,
        *,
        result: Any | None = None,
        invoke_error: Exception | None = None,
        invoke_delay: float = 0.0,
    ) -> None:
        self.result = result if result is not None else _FakeRunResult()
        self.invoke_error = invoke_error
        self.invoke_delay = invoke_delay
        self.entered = False
        self.exited = False
        self.invoke_requests: list[Any] = []

    async def __aenter__(self) -> "_FakeRuntime":
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.exited = True

    async def invoke(self, *, request: Any) -> Any:
        self.invoke_requests.append(request)
        if self.invoke_delay:
            await asyncio.sleep(self.invoke_delay)
        if self.invoke_error is not None:
            raise self.invoke_error
        return self.result


class _FakeFabric:
    def __init__(
        self,
        *,
        runtime: _FakeRuntime | None = None,
        start_error: Exception | None = None,
    ) -> None:
        self.runtime = runtime if runtime is not None else _FakeRuntime()
        self.start_error = start_error
        self.start_calls: list[dict[str, Any]] = []

    async def start_runtime(
        self,
        fabric_config: Any,
        *,
        base_dir: Path | str,
        overrides: dict[str, Any] | None = None,
    ) -> _FakeRuntime:
        self.start_calls.append(
            {
                "base_dir": base_dir,
                "fabric_config": fabric_config,
                "overrides": overrides,
            }
        )
        if self.start_error is not None:
            raise self.start_error
        return self.runtime


@pytest.mark.asyncio
class TestRunFabricAgentOnce:
    async def test_starts_invokes_and_cleans_up_ephemeral_runtime(self) -> None:
        fabric_config = cast(FabricConfig, object())
        fake_runtime = _FakeRuntime()
        fake_fabric = _FakeFabric(runtime=fake_runtime)
        request = FabricRuntimeRequest(
            fabric_config=fabric_config,
            base_dir=Path("/tmp/agent"),
            input={"prompt": "hi"},
            request_id="platform-request-1",
            caller_context={"session_id": "session-1"},
            overrides={"models": {"default": {"temperature": 0.1}}},
        )

        result = await run_fabric_agent_once(request, fabric=fake_fabric)

        assert fake_fabric.start_calls == [
            {
                "base_dir": Path("/tmp/agent"),
                "fabric_config": fabric_config,
                "overrides": {"models": {"default": {"temperature": 0.1}}},
            }
        ]
        assert fake_runtime.entered is True
        assert fake_runtime.exited is True
        fabric_request = fake_runtime.invoke_requests[0]
        assert fabric_request.input == {"prompt": "hi"}
        assert fabric_request.request_id == "platform-request-1"
        assert fabric_request.context == {"session_id": "session-1"}
        assert result.status == "succeeded"
        assert result.response == "hello"
        assert result.runtime_id == "runtime-1"
        assert result.invocation_id == "invocation-1"
        assert result.request_id == "request-1"

    async def test_wraps_timeout(self) -> None:
        fake_runtime = _FakeRuntime(invoke_delay=1.0)
        fake_fabric = _FakeFabric(runtime=fake_runtime)
        request = FabricRuntimeRequest(
            fabric_config=cast(FabricConfig, object()),
            base_dir=Path("/tmp/agent"),
            timeout_seconds=0.01,
        )

        with pytest.raises(FabricRuntimeTimeoutError, match="Fabric runtime invocation timed out after 0.01s"):
            await run_fabric_agent_once(request, fabric=fake_fabric)

        assert fake_runtime.exited is True

    async def test_wraps_fabric_lifecycle_errors(self) -> None:
        fake_fabric = _FakeFabric(start_error=fabric_runtime.FabricError("native unavailable"))
        request = FabricRuntimeRequest(
            fabric_config=cast(FabricConfig, object()),
            base_dir=Path("/tmp/agent"),
        )

        with pytest.raises(FabricRuntimeExecutionError, match="Fabric runtime invocation failed: native unavailable"):
            await run_fabric_agent_once(request, fabric=fake_fabric)

    async def test_failed_run_result_is_returned_as_normalized_result(self) -> None:
        failed_result = _FakeRunResult(
            status="failed",
            output=_FabricMapping({"response": ""}),
            error=_FabricMapping({"stage": "invoke", "message": "adapter failed"}),
        )
        fake_fabric = _FakeFabric(runtime=_FakeRuntime(result=failed_result))
        request = FabricRuntimeRequest(
            fabric_config=cast(FabricConfig, object()),
            base_dir=Path("/tmp/agent"),
        )

        result = await run_fabric_agent_once(request, fabric=fake_fabric)

        assert result.status == "failed"
        assert result.error == {"stage": "invoke", "message": "adapter failed"}


class TestNormalizeFabricRunResult:
    def test_normalizes_fabric_mapping_fields_to_plain_values(self) -> None:
        result = normalize_fabric_run_result(
            cast(
                RunResult,
                _FakeRunResult(
                    output={
                        "response": "done",
                        "messages": (_FabricMapping({"role": "assistant", "content": "done"}),),
                    },
                ),
            )
        )

        assert result.output == {
            "response": "done",
            "messages": [{"role": "assistant", "content": "done"}],
        }
        assert result.response == "done"
        assert result.artifacts == {"root": "/tmp/artifacts", "artifacts": []}
        assert result.telemetry == [{"provider": "relay", "kind": "trace"}]
        assert result.events == [{"kind": "runtime_start", "message": "started"}]
        assert result.metadata == {"adapter_runner": "python"}
