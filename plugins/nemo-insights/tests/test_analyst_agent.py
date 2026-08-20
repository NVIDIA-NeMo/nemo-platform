# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hermetic validation of the Nooa analyst harness."""

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from nemo_insights_plugin.analyst.agent import KICKOFF, Analyst, build_analyst_agent
from nemo_insights_plugin.analyst.analyst_backend import AnalystBackend
from nemo_insights_plugin.analyst.deps import AnalystDeps
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
        ethos="# Expected behavior\nBe accurate.",
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
    assert "One method, two modes" in rendered_messages
    assert "private-workspace" not in rendered_messages
    assert fake.last_tools is not None
    assert {tool.name for tool in fake.last_tools} == {"execute_python", "return_result"}


class _SpanBackend:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def list_span_groups(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {"groups": [], "count": 0, "total": 0, "truncated": False}


async def test_nooa_read_method_preserves_run_scope() -> None:
    backend = _SpanBackend()
    since = datetime(2026, 8, 1, tzinfo=UTC)
    analyst = build_analyst_agent(
        deps=AnalystDeps(
            agent="target-agent",
            workspace="workspace",
            backend=cast(AnalystBackend, backend),
            since=since,
            evaluation_id="eval-1",
        ),
        agent="target-agent",
        llm=FakeLLMClient(),
    )

    result = await analyst.fetch_spans(
        filter={"status": "error"},
        group_by="session_id",
        limit=500,
    )

    assert result["total"] == 0
    assert backend.kwargs == {
        "workspace": "workspace",
        "filter": {"status": "error", "agent_name": "target-agent"},
        "group_by": "session_id",
        "sort": "-span_count",
        "limit": 200,
        "since": since,
        "evaluation_id": "eval-1",
    }


def test_nooa_runtime_options_are_forwarded() -> None:
    analyst = build_analyst_agent(
        deps=AnalystDeps(agent="target-agent", workspace="workspace"),
        agent="target-agent",
        llm=FakeLLMClient(),
        context={"runtime_override": "forwarded"},
    )

    assert cast(Any, analyst.context)["runtime_override"] == "forwarded"
