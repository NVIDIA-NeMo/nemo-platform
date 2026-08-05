# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ``run_analyst`` client injection contract."""

from typing import cast

import pytest
from nemo_insights_plugin.analyst import run as run_module
from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_platform import AsyncNeMoPlatform
from nooa.context_blocks import ResultStatus
from nooa.events import LLMComplete, PythonOutput


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    async def persist_result(self, *, workspace: str, agent: str, result: object) -> str:
        return "REPORT"


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, seen: dict[str, object]) -> None:
    def fake_make_backend(*, client: FakeClient, insights_output: str | None) -> FakeBackend:
        seen["backend_client"] = client
        return FakeBackend()

    async def fake_run_agent(analyst: object, *, verbose: bool) -> object:
        return object()

    monkeypatch.setattr(run_module, "make_analyst_backend", fake_make_backend)

    def fake_build_agent(**kwargs: object) -> object:
        seen["build_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(run_module, "build_analyst_agent", fake_build_agent)
    monkeypatch.setattr(run_module, "_run_agent", fake_run_agent)


async def test_injected_client_is_used_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    report = await run_module.run_analyst(
        agent="agent",
        agent_spec=None,
        workspace="workspace",
        base_url="https://platform",
        client=cast(AsyncNeMoPlatform, client),
    )

    assert report == "REPORT"
    assert seen["backend_client"] is client
    build_kwargs = cast(dict[str, object], seen["build_kwargs"])
    assert cast(AnalystDeps, build_kwargs["deps"]).backend is not None
    assert client.closed


def test_litellm_compatibility_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLiteLLM:
        drop_params = False

    fake_litellm = FakeLiteLLM()
    monkeypatch.setattr(run_module.importlib, "import_module", lambda name: fake_litellm)

    run_module._enable_litellm_drop_params()

    assert fake_litellm.drop_params is True


async def test_client_closed_when_backend_construction_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()

    def raising_backend(*, client: FakeClient, insights_output: str | None) -> FakeBackend:
        raise RuntimeError("backend failed")

    monkeypatch.setattr(run_module, "make_analyst_backend", raising_backend)

    with pytest.raises(RuntimeError, match="backend failed"):
        await run_module.run_analyst(
            agent="agent",
            agent_spec=None,
            workspace="workspace",
            base_url="https://platform",
            client=cast(AsyncNeMoPlatform, client),
        )

    assert client.closed


def test_verbose_echo_maps_nooa_reasoning_tools_and_execution(capsys: pytest.CaptureFixture[str]) -> None:
    run_module._echo_event(
        LLMComplete(
            reasoning_content="inspect the failing sessions",
            tool_calls=[
                {
                    "tool_call_id": "call-1",
                    "function_name": "execute_python",
                    "arguments": '{"code":"await self.fetch_spans()"}',
                }
            ],
        )
    )
    run_module._echo_event(
        PythonOutput(
            tool_call_id="call-1",
            execution_count=1,
            execution_status=ResultStatus.COMPLETE,
            stdout="2 sessions\n",
        )
    )

    assert capsys.readouterr().err.splitlines() == [
        "[thought] inspect the failing sessions",
        '[tool] execute_python({"code":"await self.fetch_spans()"})',
        "[result] execute_python -> 2 sessions",
    ]


async def test_client_closed_when_observability_shutdown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    class FailingObservability:
        def shutdown(self) -> None:
            raise RuntimeError("shutdown failed")

    monkeypatch.setattr(run_module, "_analyst_observability_enabled", lambda: True)
    monkeypatch.setattr(
        run_module,
        "setup_analyst_observability",
        lambda **kwargs: FailingObservability(),
    )

    with pytest.raises(RuntimeError, match="shutdown failed"):
        await run_module.run_analyst(
            agent="agent",
            agent_spec=None,
            workspace="workspace",
            base_url="https://platform",
            client=cast(AsyncNeMoPlatform, client),
        )

    assert client.closed
