# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for A2A agent-card discovery (no real network; httpx mocked)."""

from __future__ import annotations

import httpx
import pytest
import respx
from nemo_agents_plugin.a2a import AgentCardError, fetch_agent_card

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
    with pytest.raises(AgentCardError, match="could not reach"):
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
