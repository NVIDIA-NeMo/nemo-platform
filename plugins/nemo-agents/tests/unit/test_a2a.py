# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for A2A agent-card discovery (no real network; httpx mocked)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from nemo_agents_plugin.a2a import (
    A2AMessageError,
    AgentCardError,
    extract_message_text,
    extract_stream_delta,
    fetch_agent_card,
    send_a2a_message,
    stream_a2a_message,
)

CARD = {"name": "Calculator Agent", "description": "does math", "skills": [{"id": "add", "name": "add"}]}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_card_from_primary_path() -> None:
    respx.get("http://host:10000/.well-known/agent-card.json").mock(return_value=httpx.Response(200, json=CARD))
    card = await fetch_agent_card("http://host:10000")
    assert card["name"] == "Calculator Agent"


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_legacy_path() -> None:
    respx.get("http://host:10000/.well-known/agent-card.json").mock(return_value=httpx.Response(404))
    respx.get("http://host:10000/.well-known/agent.json").mock(return_value=httpx.Response(200, json=CARD))
    card = await fetch_agent_card("http://host:10000")
    assert card["skills"][0]["id"] == "add"


@pytest.mark.asyncio
async def test_rejects_non_http_url() -> None:
    with pytest.raises(AgentCardError, match="http"):
        await fetch_agent_card("ftp://host")


@pytest.mark.asyncio
@respx.mock
async def test_unreachable_raises() -> None:
    respx.get("http://host:10000/.well-known/agent-card.json").mock(side_effect=httpx.ConnectError("refused"))
    respx.get("http://host:10000/.well-known/agent.json").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(AgentCardError, match="Could not fetch a valid A2A agent card"):
        await fetch_agent_card("http://host:10000")


@pytest.mark.asyncio
@respx.mock
async def test_non_card_json_rejected() -> None:
    respx.get("http://host:10000/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, json={"unrelated": True})
    )
    respx.get("http://host:10000/.well-known/agent.json").mock(
        return_value=httpx.Response(200, json={"unrelated": True})
    )
    with pytest.raises(AgentCardError):
        await fetch_agent_card("http://host:10000")


class TestExtractMessageText:
    def test_message_parts(self) -> None:
        result = {"kind": "message", "parts": [{"kind": "text", "text": "hello"}]}
        assert extract_message_text(result) == "hello"

    def test_task_artifacts(self) -> None:
        result = {
            "kind": "task",
            "artifacts": [{"parts": [{"kind": "text", "text": "42"}]}],
            "status": {"state": "completed"},
        }
        assert extract_message_text(result) == "42"

    def test_task_status_message(self) -> None:
        result = {"status": {"message": {"parts": [{"kind": "text", "text": "done"}]}}}
        assert extract_message_text(result) == "done"

    def test_no_text_returns_empty(self) -> None:
        assert extract_message_text({"artifacts": [{"parts": [{"kind": "file"}]}]}) == ""
        assert extract_message_text(None) == ""


@pytest.mark.asyncio
@respx.mock
async def test_send_message_returns_reply_text() -> None:
    route = respx.post("http://host:10000/").mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"kind": "message", "parts": [{"kind": "text", "text": "the answer"}]},
            },
        )
    )
    reply = await send_a2a_message("http://host:10000/", "what is it?")
    assert reply == "the answer"
    sent = json.loads(route.calls.last.request.content)
    assert sent["method"] == "message/send"
    assert sent["params"]["message"]["parts"][0]["text"] == "what is it?"


@pytest.mark.asyncio
@respx.mock
async def test_send_message_jsonrpc_error_raises() -> None:
    respx.post("http://host:10000/").mock(
        return_value=httpx.Response(
            200, json={"jsonrpc": "2.0", "id": "1", "error": {"code": -32000, "message": "boom"}}
        )
    )
    with pytest.raises(A2AMessageError, match="boom"):
        await send_a2a_message("http://host:10000/", "hi")


@pytest.mark.asyncio
@respx.mock
async def test_send_message_transport_error_raises() -> None:
    respx.post("http://host:10000/").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(A2AMessageError, match="could not reach"):
        await send_a2a_message("http://host:10000/", "hi")


class TestExtractStreamDelta:
    def test_message_event(self) -> None:
        assert extract_stream_delta({"kind": "message", "parts": [{"kind": "text", "text": "hi"}]}) == "hi"

    def test_artifact_update_event(self) -> None:
        event = {"kind": "artifact-update", "artifact": {"parts": [{"kind": "text", "text": "tok"}]}}
        assert extract_stream_delta(event) == "tok"

    def test_status_update_and_empty_yield_nothing(self) -> None:
        assert extract_stream_delta({"kind": "status-update", "status": {"state": "working"}}) == ""
        assert extract_stream_delta(None) == ""


@pytest.mark.asyncio
@respx.mock
async def test_stream_message_yields_deltas() -> None:
    sse = (
        ": ping\n\n"
        'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"artifact-update",'
        '"artifact":{"parts":[{"kind":"text","text":"2 + 2"}]}}}\n\n'
        'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"message",'
        '"parts":[{"kind":"text","text":" = 4"}]}}\n\n'
    )
    respx.post("http://host:10000/").mock(
        return_value=httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    )
    deltas = [d async for d in stream_a2a_message("http://host:10000/", "what is 2+2?")]
    assert deltas == ["2 + 2", " = 4"]


@pytest.mark.asyncio
@respx.mock
async def test_stream_jsonrpc_error_raises() -> None:
    sse = 'data: {"jsonrpc":"2.0","id":"1","error":{"code":-32000,"message":"kaboom"}}\n\n'
    respx.post("http://host:10000/").mock(
        return_value=httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    )
    with pytest.raises(A2AMessageError, match="kaboom"):
        _ = [d async for d in stream_a2a_message("http://host:10000/", "hi")]
