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


def _request(context: dict[str, Any] | None = None) -> contract.AgentRunRequest:
    return contract.AgentRunRequest(input="Analyze telemetry.", context=context or {})


async def test_fabric_adapter_returns_unpersisted_analyst_result(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_run_analyst_change_set(**kwargs: Any) -> tuple[AnalystResult, object]:
        seen.update(kwargs)
        return AnalystResult(summary="No high-impact failures found."), object()

    monkeypatch.setattr(fabric_adapter, "run_analyst_change_set", fake_run_analyst_change_set)
    monkeypatch.setattr(fabric_adapter, "get_async_task_sdk", lambda service: f"client:{service}")

    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start(
        {
            "config": _agent_config(
                {
                    "agent": "research-agent",
                    "agent_spec": "# Contract",
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
    assert seen["agent_spec"] == "# Contract"
    assert seen["workspace"] == "workspace"
    assert seen["base_url"] == "http://platform"
    assert seen["client"] == "client:insights"
    assert seen["since"].isoformat() == "2026-08-21T12:00:00+00:00"
    assert seen["evaluation_id"] == "eval-123"
    assert seen["model_refs"].default == "default/gpt-5"
    assert seen["model_refs"].fast == "default/gpt-5-mini"


async def test_fabric_adapter_reports_configuration_failure() -> None:
    runtime = fabric_adapter.InsightsAnalystRuntime()
    await runtime.start({"config": _agent_config({})})

    result = await runtime.invoke(_request({"job_workspace": "workspace"}), cast(contract.RuntimeContext, None))

    assert result.status is contract.AgentRunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "insights_analyst_failed"
    assert "harness.settings.agent is required" in result.error.message
