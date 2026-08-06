# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hermetic validation of the Nooa analyst harness."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from nemo_insights_plugin.analyst import model_config
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


class _FakeCompletionClient:
    def __init__(self, model: str, **config: object) -> None:
        self.model = model
        self.config = config
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


def _platform_client(*, entities: dict[str, object]) -> tuple[AsyncMock, SimpleNamespace]:
    async def retrieve(name: str, *, workspace: str) -> object:
        return entities[f"{workspace}/{name}"]

    models = SimpleNamespace(
        retrieve=AsyncMock(side_effect=retrieve),
        get_model_entity_route_openai_url=Mock(
            side_effect=lambda entity: (
                f"https://platform.example/apis/inference-gateway/v2/workspaces/"
                f"{entity.workspace}/model/{entity.name}/-/v1"
            )
        ),
        get_client_default_headers=Mock(return_value={"Authorization": "Bearer platform-token"}),
    )
    return models.retrieve, SimpleNamespace(models=models)


@pytest.mark.parametrize(
    ("smart", "fast", "default", "expected"),
    [
        (
            "default/gpt-5",
            "default/gpt-5-mini",
            "default/legacy",
            model_config.AnalystModelRefs(smart="default/gpt-5", fast="default/gpt-5-mini"),
        ),
        (
            None,
            None,
            "default/legacy",
            model_config.AnalystModelRefs(smart="default/legacy", fast="default/legacy"),
        ),
    ],
)
def test_configured_model_refs_supports_explicit_pairs_and_legacy_default(
    monkeypatch: pytest.MonkeyPatch,
    smart: str | None,
    fast: str | None,
    default: str,
    expected: model_config.AnalystModelRefs,
) -> None:
    monkeypatch.setattr(
        model_config,
        "get_context",
        lambda: SimpleNamespace(smart_model=smart, fast_model=fast, default_model=default),
    )

    assert model_config.configured_model_refs() == expected


async def test_model_pair_routes_openai_chat_via_litellm_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    entity = SimpleNamespace(
        workspace="default",
        name="gpt-5",
        backend_format="OPENAI_CHAT",
    )
    retrieve, platform = _platform_client(entities={"default/gpt-5": entity})
    monkeypatch.setattr(model_config, "CompletionClient", _FakeCompletionClient)

    pair = await model_config.resolve_model_pair(
        cast(Any, platform),
        model_config.AnalystModelRefs(smart="default/gpt-5", fast="default/gpt-5"),
    )

    smart = cast(_FakeCompletionClient, pair.smart)
    assert pair.fast is pair.smart
    assert smart.model == "openai/gpt-5"
    assert smart.config == {
        "api_base": "https://platform.example/apis/inference-gateway/v2/workspaces/default/model/gpt-5/-/v1",
        "api_key": "not-needed",
        "extra_headers": {"Authorization": "Bearer platform-token"},
    }
    retrieve.assert_awaited_once_with("gpt-5", workspace="default")

    await pair.aclose()
    assert smart.close_count == 1


async def test_model_pair_routes_anthropic_messages_without_plugin_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entities = {
        "default/claude-opus": SimpleNamespace(
            workspace="default",
            name="claude-opus",
            backend_format="ANTHROPIC_MESSAGES",
        ),
        "default/claude-haiku": SimpleNamespace(
            workspace="default",
            name="claude-haiku",
            backend_format="ANTHROPIC_MESSAGES",
        ),
    }
    retrieve, platform = _platform_client(entities=entities)
    monkeypatch.setattr(model_config, "CompletionClient", _FakeCompletionClient)

    pair = await model_config.resolve_model_pair(
        cast(Any, platform),
        model_config.AnalystModelRefs(
            smart="default/claude-opus",
            fast="default/claude-haiku",
        ),
    )

    smart = cast(_FakeCompletionClient, pair.smart)
    fast = cast(_FakeCompletionClient, pair.fast)
    assert smart.model == "anthropic/claude-opus"
    assert fast.model == "anthropic/claude-haiku"
    assert smart.config["api_base"] == (
        "https://platform.example/apis/inference-gateway/v2/workspaces/default/model/claude-opus/-"
    )
    assert fast.config["api_base"] == (
        "https://platform.example/apis/inference-gateway/v2/workspaces/default/model/claude-haiku/-"
    )
    assert retrieve.await_count == 2

    await pair.aclose()
    assert smart.close_count == 1
    assert fast.close_count == 1


async def test_model_pair_rejects_unsupported_backend_format(monkeypatch: pytest.MonkeyPatch) -> None:
    entity = SimpleNamespace(
        workspace="default",
        name="responses-only",
        backend_format="OPENAI_RESPONSES",
    )
    _, platform = _platform_client(entities={"default/responses-only": entity})
    monkeypatch.setattr(model_config, "CompletionClient", _FakeCompletionClient)

    with pytest.raises(ValueError, match="unsupported backend format 'OPENAI_RESPONSES'"):
        await model_config.resolve_model_pair(
            cast(Any, platform),
            model_config.AnalystModelRefs(
                smart="default/responses-only",
                fast="default/responses-only",
            ),
        )


def test_active_model_pair_is_run_scoped() -> None:
    smart = _FakeCompletionClient("openai/smart")
    fast = _FakeCompletionClient("openai/fast")
    pair = model_config.AnalystModelPair(smart=cast(Any, smart), fast=cast(Any, fast))

    with model_config.activate_model_pair(pair):
        assert model_config.get_smart_model() is smart
        assert model_config.get_fast_model() is fast

    with pytest.raises(RuntimeError, match="not activated"):
        model_config.get_smart_model()


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
