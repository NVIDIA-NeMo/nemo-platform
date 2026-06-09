# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent log parsing helpers shared by backend runtimes."""

from __future__ import annotations

import json
from typing import Any


def iter_agent_log_json_payloads(agent_log: str) -> list[dict[str, Any]]:
    """Return JSON dict payloads embedded in an agent log, newest-first after the full log."""
    candidates = [agent_log.strip()]
    lines = [line.strip() for line in agent_log.splitlines() if line.strip()]
    if lines:
        candidates.append(lines[-1])
        candidates.extend(reversed(lines))

    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    return payloads


def agent_log_has_workflow_error(agent_log: str) -> bool:
    """Detect AUT workflow errors returned as successful HTTP JSON payloads."""
    for payload in iter_agent_log_json_payloads(agent_log):
        if payload.get("code") == "workflow_error":
            return True
    return False
