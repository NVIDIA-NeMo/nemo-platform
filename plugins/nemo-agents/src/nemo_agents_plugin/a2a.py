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

from typing import Any
from urllib.parse import urljoin

import httpx

# Well-known paths that expose an A2A agent card. The spec moved from
# ``agent.json`` to ``agent-card.json``; try the current name first.
AGENT_CARD_PATHS = ("/.well-known/agent-card.json", "/.well-known/agent.json")

# Cap the card body so a hostile/misconfigured endpoint can't stream us an
# unbounded response. Cards are a few KB in practice.
_MAX_CARD_BYTES = 512 * 1024
_FETCH_TIMEOUT_S = 10.0


class AgentCardError(Exception):
    """Raised when an external agent's card can't be fetched or parsed."""


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
