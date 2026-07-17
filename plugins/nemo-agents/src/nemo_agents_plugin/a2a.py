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

import asyncio
import codecs
import ipaddress
import json
import logging
import os
import socket
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from nemo_agents_plugin.log_utils import scrub

logger = logging.getLogger(__name__)

# External-agent URLs are user-supplied, so the backend fetching them is an SSRF sink.
# By default reject any host that resolves to a private/loopback/link-local/reserved
# address (e.g. cloud metadata at 169.254.169.254); set this env var to allow them,
# which is needed for local dev where agents run on localhost.
_ALLOW_PRIVATE_HOSTS_ENV = "NEMO_AGENTS_ALLOW_PRIVATE_AGENT_HOSTS"

# Well-known paths that expose an A2A agent card. The spec moved from
# ``agent.json`` to ``agent-card.json``; try the current name first.
AGENT_CARD_PATHS = ("/.well-known/agent-card.json", "/.well-known/agent.json")

# Cap the card body so a hostile/misconfigured endpoint can't stream us an
# unbounded response. Cards are a few KB in practice.
_MAX_CARD_BYTES = 512 * 1024
_FETCH_TIMEOUT_S = 10.0

# Agents can take a while to answer; allow more headroom than card discovery.
_MESSAGE_TIMEOUT_S = 120.0

# Liveness probe is a quick "is the well-known path answering" check.
_PROBE_TIMEOUT_S = 5.0

# Cap message/stream bodies too — replies are larger than cards but still bounded,
# so one hostile endpoint can't OOM the shared gateway worker.
_MAX_MESSAGE_BYTES = 8 * 1024 * 1024


class AgentCardError(Exception):
    """Raised when an external agent's card can't be fetched or parsed."""


class A2AMessageError(Exception):
    """Raised when a ``message/send`` call to an external agent fails."""


class AgentHostNotAllowed(A2AMessageError):
    """Raised when an agent URL resolves to a disallowed (e.g. private/loopback) address."""


def _address_disallowed(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


async def _ensure_host_allowed(url: str) -> None:
    """Reject *url* whose host resolves to a private/loopback/link-local address.

    The SSRF guard for external-agent URLs. Bypassed by ``_ALLOW_PRIVATE_HOSTS_ENV``
    for local dev. Never surfaces the resolved address to the caller.
    """
    if os.environ.get(_ALLOW_PRIVATE_HOSTS_ENV):
        return
    host = urlparse(url).hostname
    if not host:
        raise AgentHostNotAllowed("agent endpoint has no host")
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AgentHostNotAllowed(f"could not resolve agent host ({exc.__class__.__name__})") from exc
    if any(_address_disallowed(str(info[4][0])) for info in infos):
        logger.warning("Blocked external-agent host %s: resolves to a disallowed address", _endpoint_host(url))
        raise AgentHostNotAllowed("agent host resolves to a disallowed address")


async def _read_capped(response: httpx.Response, cap: int) -> bytes:
    """Read a streamed response body incrementally, aborting once *cap* bytes are exceeded."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > cap:
            raise A2AMessageError("agent response exceeded the size limit")
        chunks.append(chunk)
    return b"".join(chunks)


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
    try:
        await _ensure_host_allowed(base)
    except AgentHostNotAllowed as exc:
        raise AgentCardError("Could not fetch a valid A2A agent card from the provided URL.") from exc

    # Log the specific reason but never surface it: distinct errors would give the
    # caller an SSRF oracle for probing internal hosts/ports.
    last_error = "no agent card found"
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_S, follow_redirects=False) as client:
        for path in AGENT_CARD_PATHS:
            url = _card_url(base, path)
            try:
                async with client.stream("GET", url, headers={"Accept": "application/json"}) as resp:
                    if resp.status_code != 200:
                        last_error = f"HTTP {resp.status_code} from {path}"
                        continue
                    try:
                        raw = await _read_capped(resp, _MAX_CARD_BYTES)
                    except A2AMessageError:
                        last_error = "card response exceeded the size limit"
                        continue
            except httpx.HTTPError as exc:
                last_error = f"transport error ({exc.__class__.__name__})"
                continue
            try:
                card = json.loads(raw)
            except ValueError:
                last_error = "card response was not valid JSON"
                continue
            if not isinstance(card, dict) or not (card.get("name") or card.get("skills")):
                last_error = "response did not look like an A2A agent card"
                continue
            return card

    logger.info("Agent card fetch failed for %s: %s", _endpoint_host(base), scrub(last_error))
    raise AgentCardError("Could not fetch a valid A2A agent card from the provided URL.")


def _endpoint_host(url: str) -> str:
    """Host of *url* for logging — avoid echoing the full URL back anywhere."""
    try:
        return urlparse(url).hostname or "unknown"
    except ValueError:
        return "unknown"


async def probe_agent_reachable(base_url: str) -> bool:
    """Cheap liveness check: does the agent's well-known card path answer 200?

    Short timeout, no redirects, no body parsing — just a reachability signal for
    the UI. Never raises; returns False on any failure.
    """
    base = base_url.strip()
    if not base.startswith(("http://", "https://")):
        return False
    try:
        await _ensure_host_allowed(base)
    except AgentHostNotAllowed:
        return False
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            for path in AGENT_CARD_PATHS:
                try:
                    # Stream so we only wait for the status line — never read the
                    # (potentially unbounded / slow-drip) body for a liveness check.
                    async with client.stream("GET", _card_url(base, path)) as resp:
                        if resp.status_code == 200:
                            return True
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        return False
    return False


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
    await _ensure_host_allowed(endpoint)
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
        async with httpx.AsyncClient(timeout=_MESSAGE_TIMEOUT_S, follow_redirects=False) as client:
            async with client.stream("POST", endpoint, json=payload, headers={"Accept": "application/json"}) as resp:
                if resp.status_code != 200:
                    raise A2AMessageError(f"agent returned HTTP {resp.status_code}")
                raw = await _read_capped(resp, _MAX_MESSAGE_BYTES)
    except httpx.HTTPError as exc:
        raise A2AMessageError(f"could not reach agent at {endpoint} ({exc.__class__.__name__})") from exc

    try:
        data = json.loads(raw)
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
    await _ensure_host_allowed(endpoint)
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
        async with httpx.AsyncClient(timeout=_MESSAGE_TIMEOUT_S, follow_redirects=False) as client:
            async with client.stream("POST", endpoint, json=payload, headers={"Accept": "text/event-stream"}) as resp:
                if resp.status_code != 200:
                    raise A2AMessageError(f"agent returned HTTP {resp.status_code}")
                # Cap raw bytes and split lines ourselves: aiter_lines() would buffer a
                # newline-less body unbounded before any per-line check runs.
                total = 0
                buffer = ""
                # Incremental decoder keeps a partial multi-byte char across chunk boundaries.
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_MESSAGE_BYTES:
                        raise A2AMessageError("agent stream exceeded the size limit")
                    buffer += decoder.decode(chunk)
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
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
