# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ``run_analyst`` client injection contract."""

from typing import Any, cast

import pytest
from nemo_insights_plugin.analyst import run as run_module
from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.observability import AnalystEvaluationContext
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.nooa_model_client import ConfiguredModelClients
from nooa.context_blocks import ResultStatus
from nooa.events import LLMComplete, PythonOutput


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeModelClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeBackend:
    async def persist_result(self, *, workspace: str, agent: str, result: object) -> str:
        return "REPORT"


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, seen: dict[str, object]) -> None:
    default = FakeModelClient()
    fast = FakeModelClient()
    model_clients = ConfiguredModelClients(
        default=cast(Any, default),
        fast=cast(Any, fast),
    )

    async def fake_resolve_model_clients(client: object, refs: object) -> ConfiguredModelClients:
        seen["model_client"] = client
        seen["model_refs"] = refs
        seen["model_clients"] = model_clients
        return model_clients

    def fake_make_backend(*, client: FakeClient, insights_output: str | None, local_only: bool) -> FakeBackend:
        seen["backend_client"] = client
        seen["local_only"] = local_only
        return FakeBackend()

    async def fake_run_agent(analyst: object, *, verbose: bool) -> object:
        return object()

    monkeypatch.setattr(run_module, "make_analyst_backend", fake_make_backend)
    monkeypatch.setattr(run_module, "resolve_model_clients", fake_resolve_model_clients)

    def fake_build_agent(**kwargs: object) -> object:
        seen["build_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(run_module, "build_analyst_agent", fake_build_agent)
    monkeypatch.setattr(run_module, "_run_agent", fake_run_agent)

    class Observability:
        def shutdown(self) -> None:
            seen["shutdown"] = True

    monkeypatch.setattr(run_module, "setup_analyst_observability", lambda **_kwargs: Observability())


async def test_injected_client_is_used_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    report = await run_module.run_analyst(
        agent="agent",
        ethos=None,
        workspace="workspace",
        base_url="https://platform",
        client=cast(AsyncNeMoPlatform, client),
    )

    assert report == "REPORT"
    assert seen["backend_client"] is client
    build_kwargs = cast(dict[str, object], seen["build_kwargs"])
    assert cast(AnalystDeps, build_kwargs["deps"]).backend is not None
    assert seen["model_client"] is client
    model_clients = cast(ConfiguredModelClients, seen["model_clients"])
    assert cast(FakeModelClient, model_clients.default).closed
    assert cast(FakeModelClient, model_clients.fast).closed
    assert client.closed


async def test_client_closed_when_backend_construction_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    model = FakeModelClient()
    pair = ConfiguredModelClients(
        default=cast(Any, model),
        fast=cast(Any, model),
    )

    async def fake_resolve_model_clients(client: object, refs: object) -> ConfiguredModelClients:
        return pair

    def raising_backend(*, client: FakeClient, insights_output: str | None, local_only: bool) -> FakeBackend:
        raise RuntimeError("backend failed")

    monkeypatch.setattr(run_module, "resolve_model_clients", fake_resolve_model_clients)
    monkeypatch.setattr(run_module, "make_analyst_backend", raising_backend)

    with pytest.raises(RuntimeError, match="backend failed"):
        await run_module.run_analyst(
            agent="agent",
            ethos=None,
            workspace="workspace",
            base_url="https://platform",
            client=cast(AsyncNeMoPlatform, client),
        )

    assert model.closed
    assert client.closed


async def test_client_closed_when_model_resolution_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()

    async def raising_model_resolution(client: object, refs: object) -> ConfiguredModelClients:
        raise RuntimeError("model resolution failed")

    monkeypatch.setattr(run_module, "resolve_model_clients", raising_model_resolution)

    with pytest.raises(RuntimeError, match="model resolution failed"):
        await run_module.run_analyst(
            agent="agent",
            ethos=None,
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
    monkeypatch.setenv(run_module.ANALYST_OBSERVABILITY_ENV, "true")

    class FailingObservability:
        def shutdown(self) -> None:
            raise RuntimeError("shutdown failed")

    monkeypatch.setattr(
        run_module,
        "setup_analyst_observability",
        lambda **kwargs: FailingObservability(),
    )

    with pytest.raises(RuntimeError, match="shutdown failed"):
        await run_module.run_analyst(
            agent="agent",
            ethos=None,
            workspace="workspace",
            base_url="https://platform",
            client=cast(AsyncNeMoPlatform, client),
        )

    assert client.closed


async def test_evaluation_context_is_forwarded_to_default_on_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    class Observability:
        def shutdown(self) -> None:
            seen["shutdown"] = True

    def fake_setup(**kwargs: object) -> Observability:
        seen["observability"] = kwargs
        return Observability()

    monkeypatch.setattr(run_module, "setup_analyst_observability", fake_setup)
    evaluation_context = AnalystEvaluationContext(
        evaluation_name="nemo-analyst-1",
        test_case_name="smoke/g1",
    )

    await run_module.run_analyst(
        agent="smoke-agent",
        agent_spec=None,
        workspace="default",
        base_url="http://localhost:8080",
        client=cast(AsyncNeMoPlatform, client),
        analyst_evaluation=evaluation_context,
    )

    assert seen["observability"] == {
        "base_url": "http://localhost:8080",
        "workspace": "default",
        "target_agent": "smoke-agent",
        "evaluation_context": evaluation_context,
    }
    assert seen["shutdown"] is True


async def test_per_run_observability_opt_out_skips_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    def fail_setup(**kwargs: object) -> None:
        raise AssertionError(f"unexpected observability setup: {kwargs}")

    monkeypatch.setattr(run_module, "setup_analyst_observability", fail_setup)

    await run_module.run_analyst(
        agent="remote-agent",
        agent_spec=None,
        workspace="default",
        base_url="https://remote.example",
        client=cast(AsyncNeMoPlatform, client),
        enable_observability=False,
    )

    assert client.closed
