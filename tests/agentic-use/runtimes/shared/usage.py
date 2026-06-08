# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Token usage extraction from agent logs.

Reuses the proven implementation from ``nat_runner.py`` until the legacy
runner delegates here and the duplicate can be removed.
"""

from __future__ import annotations

from typing import TypedDict


class TokenMetrics(TypedDict):
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cache_creation_tokens: int | None
    cache_read_tokens: int | None
    n_assistant_messages: int | None
    cost_usd: float | None
    num_turns: int | None
    duration_ms: float | None


def extract_usage_metrics(agent_log: str) -> dict[str, int | float | None]:
    """Extract token usage metrics from an agent log."""
    import nat_runner

    metrics = nat_runner._extract_usage_metrics(agent_log)
    return dict(metrics)
