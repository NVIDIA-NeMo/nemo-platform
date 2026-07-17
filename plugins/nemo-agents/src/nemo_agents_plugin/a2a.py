# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A2A (Agent-to-Agent) discovery helpers.

An externally-running NAT agent served with ``nat a2a serve`` publishes an
*agent card* at a well-known path. The card describes the agent (name,
description) and its skills (one per workflow function). We fetch it at
registration time so the platform can list and visualize an agent it does not
run. See https://github.com/nvidia/nemo-agent-toolkit A2A server docs.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import httpx

# Well-known paths that expose an A2A agent card. The spec moved from
# ``agent.json`` to ``agent-card.json``; try the current name first.
AGENT_CARD_PATHS = ("/.well-known/agent-card.json", "/.well-known/agent.json")

# Cap the card body so a hostile/misconfigured endpoint can't stream us an
# unbounded response. Cards are a few KB in practice.
_MAX_CARD_BYTES = 512 * 1024
_FETCH_TIMEOUT_S = 10.0

# Agents can take a while to answer; allow more headroom than card discovery.
_MESSAGE_TIMEOUT_S = 120.0


class AgentCardError(Exception):
    """Raised when an external agent's card can't be fetched or parsed."""


class A2AMessageError(Exception):
    """Raised when a ``message/send`` call to an external agent fails."""


def _card_url(base_url: str, path: str) -> str:
    # urljoin needs a trailing slash on the base to preserve any path prefix,
    # and the well-known path is absolute, so join against the origin.
    return urljoin(base_url if base_url.endswith("/") else base_url + "/", path.lstrip("/"))


async def fetch_agent_card(base_url: str) -> dict[str, Any]:
    """Fetch and parse an external agent's A2A card.

    Tries each well-known path in order. Raises :class:`AgentCardError` with a
    user-facing message if the endpoint is unreachable, returns non-JSON, or
    exposes no recognizable card. The returned dict is the raw card.
    """
    base = base_url.strip()
    if not base.startswith(("http://", "https://")):
        raise AgentCardError("Endpoint must be an http(s) URL.")

    last_error = "no agent card found"
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_S, follow_redirects=True) as client:
        for path in AGENT_CARD_PATHS:
            url = _card_url(base, path)
            try:
                resp = await client.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                last_error = f"could not reach agent at {base} ({exc.__class__.__name__})"
                continue
            if resp.status_code != 200:
                last_error = f"agent card request returned HTTP {resp.status_code}"
                continue
            if len(resp.content) > _MAX_CARD_BYTES:
                raise AgentCardError("Agent card response is too large.")
            try:
                card = resp.json()
            except ValueError:
                last_error = "agent card response was not valid JSON"
                continue
            if not isinstance(card, dict) or not (card.get("name") or card.get("skills")):
                last_error = "response did not look like an A2A agent card"
                continue
            return card

    raise AgentCardError(f"Could not fetch A2A agent card: {last_error}.")


def _collect_text_parts(parts: Any) -> list[str]:
    """Pull the text out of an A2A ``parts`` array, ignoring non-text parts."""
    out: list[str] = []
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"]:
                out.append(part["text"])
    return out


def extract_message_text(result: Any) -> str:
    """Extract assistant text from an A2A ``message/send`` result.

    The result is either a Message (``parts`` directly) or a Task (text lives in
    ``artifacts[].parts`` and/or ``status.message.parts``). Concatenate whatever
    text parts are present; return "" if none.
    """
    if not isinstance(result, dict):
        return ""
    texts: list[str] = []
    texts += _collect_text_parts(result.get("parts"))
    artifacts = result.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                texts += _collect_text_parts(artifact.get("parts"))
    status = result.get("status")
    if isinstance(status, dict) and isinstance(status.get("message"), dict):
        texts += _collect_text_parts(status["message"].get("parts"))
    return "\n".join(texts)


async def send_a2a_message(endpoint: str, text: str) -> str:
    """Send *text* to an external A2A agent via ``message/send`` and return its reply.

    Speaks A2A JSON-RPC 2.0 directly (no A2A client dependency). Raises
    :class:`A2AMessageError` on transport failure, a JSON-RPC error, or a
    non-JSON response.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": uuid4().hex,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": uuid4().hex,
                "kind": "message",
            }
        },
    }
    try:
        async with httpx.AsyncClient(timeout=_MESSAGE_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.post(endpoint, json=payload, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise A2AMessageError(f"could not reach agent at {endpoint} ({exc.__class__.__name__})") from exc

    if resp.status_code != 200:
        raise A2AMessageError(f"agent returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise A2AMessageError("agent response was not valid JSON") from exc

    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise A2AMessageError(f"agent error: {msg}")

    return extract_message_text(data.get("result") if isinstance(data, dict) else None)


def extract_stream_delta(result: Any) -> str:
    """Extract the text delta from a single A2A ``message/stream`` event result.

    Streaming events are Messages (``parts``), artifact updates (``artifact.parts``),
    or status updates (skipped — usually just lifecycle state). Returns "" for
    events carrying no text.
    """
    if not isinstance(result, dict):
        return ""
    artifact = result.get("artifact")
    if isinstance(artifact, dict):
        return "".join(_collect_text_parts(artifact.get("parts")))
    if result.get("kind") == "message" or "parts" in result:
        return "".join(_collect_text_parts(result.get("parts")))
    return ""


async def stream_a2a_message(endpoint: str, text: str) -> AsyncIterator[str]:
    """Stream an external A2A agent's reply via ``message/stream``, yielding text deltas.

    Speaks A2A JSON-RPC over SSE. Agents that stream tokens (artifact-update
    deltas) yield incrementally; agents that buffer (e.g. NAT react_agent) yield
    a single final chunk. Raises :class:`A2AMessageError` on transport/JSON-RPC
    failure before the first token; mid-stream transport drops end the iterator.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": uuid4().hex,
        "method": "message/stream",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": uuid4().hex,
                "kind": "message",
            }
        },
    }
    try:
        async with httpx.AsyncClient(timeout=_MESSAGE_TIMEOUT_S, follow_redirects=True) as client:
            async with client.stream("POST", endpoint, json=payload, headers={"Accept": "text/event-stream"}) as resp:
                if resp.status_code != 200:
                    raise A2AMessageError(f"agent returned HTTP {resp.status_code}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):  # keepalive / comment
                        continue
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[len("data:") :].strip())
                    except ValueError:
                        continue
                    if isinstance(data, dict) and data.get("error"):
                        err = data["error"]
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        raise A2AMessageError(f"agent error: {msg}")
                    delta = extract_stream_delta(data.get("result") if isinstance(data, dict) else None)
                    if delta:
                        yield delta
    except httpx.HTTPError as exc:
        raise A2AMessageError(f"could not reach agent at {endpoint} ({exc.__class__.__name__})") from exc
