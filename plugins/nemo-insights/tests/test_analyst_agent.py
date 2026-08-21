# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hermetic validation of the Nooa analyst harness."""

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from nemo_insights_plugin.analyst.agent import KICKOFF, Analyst, build_analyst_agent
from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_platform_plugin.trace_provider import TraceProvider, TraceQuery, TraceRef, TraceRow
from nooa.unifiedllm import FakeLLMClient, LLMResponse, ToolCall


@pytest.fixture(autouse=True)
def _use_fake_summarizer_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_insights_plugin.analyst.agent.get_fast_model",
        FakeLLMClient,
    )


def _exec_response(code: str) -> LLMResponse:
    return LLMResponse(
        raw_response=None,
        content="",
        finish_reason="tool_calls",
        assistant_message={"role": "assistant", "content": ""},
        tool_calls=[
            ToolCall(
                id="call_exec",
                name="execute_python",
                arguments=json.dumps({"code": code}),
            )
        ],
    )


async def test_nooa_codeact_returns_typed_analyst_result_and_receives_prompt() -> None:
    fake = FakeLLMClient(
        scripted_responses=[
            _exec_response(
                "return_result(result={"
                "'summary': 'No high-impact failures found.', "
                "'new_insights': [], 'updated_insights': []})"
            )
        ]
    )
    analyst = build_analyst_agent(
        deps=AnalystDeps(agent="target-agent", workspace="private-workspace"),
        agent="target-agent",
        agent_spec="# Expected behavior\nBe accurate.",
        llm=fake,
    )

    result = await analyst.analyze(KICKOFF)

    assert isinstance(analyst, Analyst)
    assert result.summary == "No high-impact failures found."
    assert result.new_insights == []
    assert result.updated_insights == []
    rendered_messages = json.dumps(fake.last_messages)
    assert "target-agent" in rendered_messages
    assert "Expected behavior" in rendered_messages
    assert "provider-native" in rendered_messages
    assert "private-workspace" not in rendered_messages
    assert fake.last_tools is not None
    assert {tool.name for tool in fake.last_tools} == {"execute_python", "return_result"}


class _TraceProvider:
    name = "test"

    def __init__(self) -> None:
        self.query: TraceQuery | None = None

    async def filter_traces(self, query: TraceQuery):
        self.query = query
        if False:
            yield TraceRef("unused")

    async def read_traces(self, traces):
        async for trace in traces:
            yield TraceRow(id=trace.id, data={})


async def test_nooa_read_method_preserves_run_scope() -> None:
    provider = _TraceProvider()
    since = datetime(2026, 8, 1, tzinfo=UTC)
    analyst = build_analyst_agent(
        deps=AnalystDeps(
            agent="target-agent",
            workspace="workspace",
            trace_provider=cast(TraceProvider, provider),
            since=since,
            evaluation_id="eval-1",
        ),
        agent="target-agent",
        llm=FakeLLMClient(),
    )

    result = await analyst.filter_traces(
        has_error=True,
        limit=500,
    )

    assert result["count"] == 0
    assert provider.query == TraceQuery(started_after=since, has_error=True, limit=201)


async def test_nooa_filter_traces_rejects_non_positive_limit() -> None:
    analyst = build_analyst_agent(
        deps=AnalystDeps(
            agent="target-agent",
            workspace="workspace",
            trace_provider=cast(TraceProvider, _TraceProvider()),
        ),
        agent="target-agent",
        llm=FakeLLMClient(),
    )

    with pytest.raises(ValueError, match="limit must be at least 1"):
        await analyst.filter_traces(limit=0)


def test_nooa_runtime_options_are_forwarded() -> None:
    analyst = build_analyst_agent(
        deps=AnalystDeps(agent="target-agent", workspace="workspace"),
        agent="target-agent",
        llm=FakeLLMClient(),
        context={"runtime_override": "forwarded"},
    )

    assert cast(Any, analyst.context)["runtime_override"] == "forwarded"
