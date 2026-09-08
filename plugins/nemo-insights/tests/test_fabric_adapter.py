# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fabric adapter contract for the Insights analyst."""

from __future__ import annotations

from typing import Any, cast

from nemo_fabric_adapter_contract import models as contract
from nemo_insights_plugin import fabric_adapter
from nemo_insights_plugin.analyst.result import AnalystResult


def _agent_config(settings: dict[str, Any]) -> contract.AgentConfig:
    return contract.AgentConfig.from_mapping(
        {
            "harness": {"settings": settings},
            "models": {
                "default": {
                    "provider": "platform",
                    "model": "default/gpt-5",
                },
                "fast": {
                    "provider": "platform",
                    "model": "default/gpt-5-mini",
                },
            },
        }
    )


class _StubClient:
    """Stands in for the async SDK handle so a leak shows up as an unclosed client."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.closed = False

    async def __aenter__(self) -> _StubClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.closed = True


def _stub_sdk_factory(clients: list[_StubClient]) -> Any:
    """Record every client handed out so a test can assert none were left open."""

    def factory(service: str) -> _StubClient:
        client = _StubClient(service)
        clients.append(client)
        return client

    return factory


def _request(context: dict[str, Any] | None = None) -> contract.AgentRunRequest:
    return contract.AgentRunRequest(input="Analyze telemetry.", context=context or {})


async def test_fabric_adapter_returns_unpersisted_analyst_result(monkeypatch) -> None:
    seen: dict[str, Any] = {}
    clients: list[_StubClient] = []

    async def fake_run_analyst_change_set(**kwargs: Any) -> tuple[AnalystResult, object]:
        seen.update(kwargs)
        return AnalystResult(summary="No high-impact failures found."), object()

    monkeypatch.setattr(fabric_adapter, "run_analyst_change_set", fake_run_analyst_change_set)
    monkeypatch.setattr(fabric_adapter, "get_async_task_sdk", _stub_sdk_factory(clients))

    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start(
        {
            "config": _agent_config(
                {
                    "agent": "research-agent",
                    "ethos": "# Ethos",
                    "base_url": "http://platform",
                    "since": "2026-08-21T12:00:00+00:00",
                    "evaluation_id": "eval-123",
                }
            )
        }
    )

    result = await runtime.invoke(_request({"job_workspace": "workspace"}), cast(contract.RuntimeContext, None))

    assert result.status is contract.AgentRunStatus.SUCCEEDED
    assert result.output == {
        "response": "No high-impact failures found.",
        "analyst_result": {
            "summary": "No high-impact failures found.",
            "new_insights": [],
            "updated_insights": [],
        },
    }
    assert seen["agent"] == "research-agent"
    assert seen["ethos"] == "# Ethos"
    assert seen["workspace"] == "workspace"
    assert seen["base_url"] == "http://platform"
    assert seen["client"] is clients[0]
    assert clients[0].service == "insights"
    assert seen["since"].isoformat() == "2026-08-21T12:00:00+00:00"
    assert seen["evaluation_id"] == "eval-123"
    assert seen["model_refs"].default == "default/gpt-5"
    assert seen["model_refs"].fast == "default/gpt-5-mini"
    # The adapter owns the client now, so a successful run must close it too.
    assert clients[0].closed


async def test_fabric_adapter_does_not_leak_a_client_when_a_model_ref_is_invalid(monkeypatch) -> None:
    """A settings error must resolve before the ``async with`` opens a client at all."""
    clients: list[_StubClient] = []

    async def fail_if_called(**kwargs: Any) -> tuple[AnalystResult, object]:
        raise AssertionError("run_analyst_change_set should not be reached")

    monkeypatch.setattr(fabric_adapter, "get_async_task_sdk", _stub_sdk_factory(clients))
    monkeypatch.setattr(fabric_adapter, "run_analyst_change_set", fail_if_called)

    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start({"config": _agent_config({"agent": "research-agent", "default_model": "   "})})

    result = await runtime.invoke(_request({"job_workspace": "workspace"}), cast(contract.RuntimeContext, None))

    assert result.status is contract.AgentRunStatus.FAILED
    assert result.error is not None
    assert "harness.settings.default_model must be a non-empty string" in result.error.message
    assert all(client.closed for client in clients), "an SDK client was built and never closed"


async def test_fabric_adapter_reports_configuration_failure() -> None:
    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start({"config": _agent_config({})})

    result = await runtime.invoke(_request({"job_workspace": "workspace"}), cast(contract.RuntimeContext, None))

    assert result.status is contract.AgentRunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "insights_analyst_failed"
    assert "harness.settings.agent is required" in result.error.message


async def test_fabric_adapter_logs_the_failure_with_its_traceback(monkeypatch, caplog) -> None:
    """``str(error)`` alone loses the traceback, and the adapter's stderr is
    captured to a run artifact the job dumps on failure - so logging here is
    what puts the traceback somewhere anyone will actually read."""
    clients: list[_StubClient] = []

    async def fail(**kwargs: Any) -> tuple[AnalystResult, object]:
        raise RuntimeError("gateway returned 502")

    monkeypatch.setattr(fabric_adapter, "run_analyst_change_set", fail)
    monkeypatch.setattr(fabric_adapter, "get_async_task_sdk", _stub_sdk_factory(clients))

    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start({"config": _agent_config({"agent": "research-agent"})})

    with caplog.at_level("ERROR", logger="nemo_insights_plugin.fabric_adapter"):
        result = await runtime.invoke(_request({"job_workspace": "workspace"}), cast(contract.RuntimeContext, None))

    assert result.status is contract.AgentRunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "insights_analyst_failed"
    assert "Insights analyst run failed." in caplog.text
    assert "gateway returned 502" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text


async def test_fabric_adapter_logs_the_whole_cause_chain(monkeypatch, caplog) -> None:
    """The originating error is what distinguishes one failure from another:
    an LLM error raised after retries reads identically whatever provoked it."""
    clients: list[_StubClient] = []

    originating = "Function 'abc-123': Not found for account"
    raised = "LLM API error after 3 retries"

    async def fail(**kwargs: Any) -> tuple[AnalystResult, object]:
        try:
            raise ValueError(originating)
        except ValueError as cause:
            raise RuntimeError(raised) from cause

    monkeypatch.setattr(fabric_adapter, "run_analyst_change_set", fail)
    monkeypatch.setattr(fabric_adapter, "get_async_task_sdk", _stub_sdk_factory(clients))

    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start({"config": _agent_config({"agent": "research-agent"})})

    with caplog.at_level("ERROR", logger="nemo_insights_plugin.fabric_adapter"):
        await runtime.invoke(_request({"job_workspace": "workspace"}), cast(contract.RuntimeContext, None))

    assert originating in caplog.text, "root cause was dropped"
    assert raised in caplog.text
