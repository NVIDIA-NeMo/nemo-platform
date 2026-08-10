# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ``run_analyst`` client injection and memory round-trip contracts."""

from collections.abc import Sequence
from typing import Any, cast

import pytest
from nemo_insights_plugin.analyst import run as run_module
from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.memory import AUTO_START, replace_auto_zone
from nemo_insights_plugin.analyst.result import AnalystResult, MemoryNote
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.nooa_model_client import ConfiguredModelClients
from nooa.context_blocks import ResultStatus
from nooa.events import LLMComplete, PythonOutput


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class InMemoryStore:
    """A ``MemoryStore`` over a string, using the real document format.

    Fileset transport is covered in ``test_analyst_memory``; this double exists
    so the run-level tests exercise the wiring and the round trip without a
    platform.
    """

    def __init__(self, document: str = "") -> None:
        self.document = document

    async def read(self) -> str:
        return self.document

    async def write(self, notes: Sequence[MemoryNote]) -> str:
        if not notes:
            return "- memory: unchanged (no notes returned)"
        self.document, _ = replace_auto_zone(self.document, notes, agent="agent", stamp="2026-08-10")
        return f"- memory: wrote {len(notes)} note(s)"


class FakeModelClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeBackend:
    async def persist_result(self, *, workspace: str, agent: str, result: object) -> str:
        return "REPORT"


def _stub_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    seen: dict[str, object],
    result: AnalystResult | None = None,
) -> None:
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

    async def fake_run_agent(analyst: object, *, verbose: bool) -> AnalystResult:
        return result if result is not None else AnalystResult(summary="nothing worth filing")

    monkeypatch.setattr(run_module, "make_analyst_backend", fake_make_backend)
    monkeypatch.setattr(run_module, "resolve_model_clients", fake_resolve_model_clients)

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
        memory_store=InMemoryStore(),
    )

    assert report.startswith("REPORT")
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
            agent_spec=None,
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


HUMAN_ZONE = """# Agent memory: agent

## Context from the developer
- `search_web` times out at 30s deliberately. Not a bug.
"""


async def test_memory_round_trips_from_one_run_into_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run replaces only the maintained zone, and the next run reads it back."""
    seen: dict[str, object] = {}
    _stub_pipeline(
        monkeypatch,
        seen,
        AnalystResult(summary="s", memory=[MemoryNote(note="eval spans are synthetic", source="t1")]),
    )
    store = InMemoryStore(HUMAN_ZONE)

    report = await run_module.run_analyst(
        agent="agent",
        agent_spec=None,
        workspace="workspace",
        base_url="https://platform",
        client=cast(AsyncNeMoPlatform, FakeClient()),
        memory_store=store,
    )

    assert cast(dict[str, object], seen["build_kwargs"])["agent_memory"] == HUMAN_ZONE
    assert store.document.startswith(HUMAN_ZONE.rstrip())
    assert "- eval spans are synthetic (2026-08-10; t1)" in store.document
    assert report.endswith("- memory: wrote 1 note(s)")

    _stub_pipeline(monkeypatch, seen, AnalystResult(summary="s"))
    await run_module.run_analyst(
        agent="agent",
        agent_spec=None,
        workspace="workspace",
        base_url="https://platform",
        client=cast(AsyncNeMoPlatform, FakeClient()),
        memory_store=store,
    )

    carried = cast(str, cast(dict[str, object], seen["build_kwargs"])["agent_memory"])
    assert "eval spans are synthetic" in carried
    assert AUTO_START in carried


async def test_store_is_derived_from_the_run_client_so_scheduled_runs_need_no_extra_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The job passes no memory config; the store comes from client/workspace/agent."""
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)
    built: dict[str, object] = {}

    class RecordingStore(InMemoryStore):
        def __init__(self, *, client: object, workspace: str, agent: str) -> None:
            super().__init__()
            built.update(client=client, workspace=workspace, agent=agent)

    monkeypatch.setattr(run_module, "FilesetMemoryStore", RecordingStore)
    client = FakeClient()

    await run_module.run_analyst(
        agent="research-agent",
        agent_spec=None,
        workspace="prod",
        base_url="https://platform",
        client=cast(AsyncNeMoPlatform, client),
    )

    assert built == {"client": client, "workspace": "prod", "agent": "research-agent"}


async def test_local_only_testbed_runs_skip_memory_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    def unreachable(**kwargs: object) -> object:
        raise AssertionError("local-only runs must not touch the platform for memory")

    monkeypatch.setattr(run_module, "FilesetMemoryStore", unreachable)

    report = await run_module.run_analyst(
        agent="agent",
        agent_spec=None,
        workspace="workspace",
        base_url="https://platform",
        client=cast(AsyncNeMoPlatform, FakeClient()),
        insights_output="insights.yaml",
        local_only=True,
    )

    assert report == "REPORT"
    assert cast(dict[str, object], seen["build_kwargs"])["agent_memory"] is None


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
            memory_store=InMemoryStore(),
        )

    assert client.closed
