# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The ``run_analyst`` client injection contract."""

from pathlib import Path

import httpx
import pytest
from nemo_insights_plugin.analyst import run as run_module


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, seen: dict[str, object]) -> None:
        self.seen = seen

    async def list_insights(self, **kwargs: object) -> None:
        self.seen["preflight"] = kwargs

    async def persist_result(self, *, workspace: str, agent: str, result: object) -> str:
        return "REPORT"


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, seen: dict[str, object]) -> None:
    def fake_make_backend(*, client: FakeClient, insights_output: str | None) -> FakeBackend:
        seen["backend_client"] = client
        return FakeBackend(seen)

    async def fake_run_agent(analyst: object, deps: object, *, verbose: bool) -> object:
        seen["agent_saw_preflight"] = "preflight" in seen
        return object()

    monkeypatch.setattr(run_module, "make_analyst_backend", fake_make_backend)
    monkeypatch.setattr(run_module, "build_analyst_agent", lambda **kwargs: object())
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
        client=client,  # type: ignore[arg-type]
    )

    assert report == "REPORT"
    assert seen["backend_client"] is client
    assert seen["preflight"] == {
        "workspace": "workspace",
        "page": 1,
        "page_size": 1,
        "agent": "agent",
        "status": None,
    }
    assert seen["agent_saw_preflight"] is True
    assert client.closed


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
            client=client,  # type: ignore[arg-type]
        )

    assert client.closed


async def test_insights_service_failure_stops_before_generation_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    agent_called = False

    class UnavailableBackend(FakeBackend):
        async def list_insights(self, **kwargs: object) -> None:
            request = httpx.Request(
                "GET",
                "https://platform/apis/insights/v2/workspaces/workspace/insights",
            )
            raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(
        run_module,
        "make_analyst_backend",
        lambda **kwargs: UnavailableBackend({}),
    )

    async def record_agent_call(analyst: object, deps: object, *, verbose: bool) -> object:
        nonlocal agent_called
        agent_called = True
        return object()

    monkeypatch.setattr(run_module, "_run_agent", record_agent_call)

    with pytest.raises(
        run_module.InsightsServiceUnavailableError,
        match="Start the Insights service and retry",
    ):
        await run_module.run_analyst(
            agent="agent",
            agent_spec=None,
            workspace="workspace",
            base_url="https://platform",
            client=client,  # type: ignore[arg-type]
        )

    assert agent_called is False
    assert client.closed


async def test_local_insights_output_skips_remote_service_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient()
    seen: dict[str, object] = {}
    _stub_pipeline(monkeypatch, seen)

    report = await run_module.run_analyst(
        agent="agent",
        agent_spec=None,
        workspace="workspace",
        base_url="https://platform",
        client=client,  # type: ignore[arg-type]
        insights_output=tmp_path / "insights.yaml",
    )

    assert report == "REPORT"
    assert "preflight" not in seen
    assert seen["agent_saw_preflight"] is False
    assert client.closed


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
            client=client,  # type: ignore[arg-type]
        )

    assert client.closed
