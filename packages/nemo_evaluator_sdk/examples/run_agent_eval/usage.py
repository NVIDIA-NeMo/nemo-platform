# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Token-usage extraction ported from ``tests/agentic-use/nat_runner.py``.

Reports the same token/runtime measurements ``nat_runner`` writes into
``result.json["metrics"]`` (the keys the SDK's ``TrialMeasurements`` reads):
``prompt_tokens``/``completion_tokens``/``cache_creation_tokens``/
``cache_read_tokens`` plus their ``total_tokens`` sum, and ``duration_ms``
(the ``runtime_sec`` fallback). Buckets follow Anthropic's prompt-caching shape
so AUT (``nemo agents invoke``) and other backends are comparable.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict


class TokenMetrics(TypedDict):
    """Token usage metrics returned by :func:`extract_usage_metrics`."""

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cache_creation_tokens: int | None
    cache_read_tokens: int | None
    duration_ms: float | None


def iter_agent_log_json_payloads(agent_log: str) -> list[dict[str, Any]]:
    """Return JSON dict payloads embedded in an agent log, newest-first after the full log."""
    candidates = [agent_log.strip()]
    lines = [ln.strip() for ln in agent_log.splitlines() if ln.strip()]
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
    return any(payload.get("code") == "workflow_error" for payload in iter_agent_log_json_payloads(agent_log))


def _first_int(usage_obj: dict[str, Any], keys: tuple[str, ...]) -> tuple[int | None, bool]:
    for key in keys:
        value = usage_obj.get(key)
        if isinstance(value, int):
            return value, True
    return None, False


def _bucket_from_usage(usage_obj: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None, bool]:
    """Return ``(input, output, cache_creation, cache_read, has_known_key)``."""
    input_tokens, has_input = _first_int(usage_obj, ("input_tokens", "prompt_tokens", "inputTokens"))
    output_tokens, has_output = _first_int(usage_obj, ("output_tokens", "completion_tokens", "outputTokens"))
    cache_creation_tokens, has_cache_creation = _first_int(
        usage_obj, ("cache_creation_input_tokens", "cacheWriteTokens")
    )
    cache_read_tokens, has_cache_read = _first_int(
        usage_obj, ("cache_read_input_tokens", "cacheReadTokens", "cached_input_tokens")
    )
    details = usage_obj.get("input_token_details")
    if isinstance(details, dict):
        if not has_cache_creation:
            cache_creation_tokens, has_cache_creation = _first_int(details, ("cache_creation",))
        if not has_cache_read:
            cache_read_tokens, has_cache_read = _first_int(details, ("cache_read",))
    if (
        "cached_input_tokens" in usage_obj
        and has_input
        and has_cache_read
        and input_tokens is not None
        and cache_read_tokens is not None
    ):
        input_tokens = max(input_tokens - cache_read_tokens, 0)
    has_known_key = has_input or has_output or has_cache_creation or has_cache_read
    return input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, has_known_key


def _looks_usage_bearing(d: dict[str, Any]) -> bool:
    """Heuristic: does this dict contain something we can extract usage from?"""
    if "messages" in d:
        return True
    return any(
        isinstance(d.get(key), dict) for key in ("usage", "usage_metadata", "response_metadata", "data", "metrics")
    )


def extract_usage_metrics(agent_log: str) -> TokenMetrics:
    """Extract token usage metrics from an agent log.

    Aggregates across **all** assistant turns when the payload exposes a
    ``messages[]`` array (the AUT shape from ``nemo agents invoke``); falls back
    to a flat top-level ``usage`` block otherwise. Returns all-``None`` when no
    known usage shape is present (e.g. plain ``nat run`` text logs).
    """
    zero: TokenMetrics = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cache_creation_tokens": None,
        "cache_read_tokens": None,
        "duration_ms": None,
    }
    if not agent_log.strip():
        return zero

    payload: dict[str, Any] | None = None
    fallback_payload: dict[str, Any] | None = None
    for parsed in iter_agent_log_json_payloads(agent_log):
        if _looks_usage_bearing(parsed):
            payload = parsed
            break
        if fallback_payload is None:
            fallback_payload = parsed
    if payload is None:
        payload = fallback_payload
    if not payload:
        return zero

    payload_candidates: list[dict[str, Any]] = [payload]
    nested_data = payload.get("data")
    if isinstance(nested_data, dict):
        payload_candidates.append(nested_data)

    sums = {"input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0}
    bucket_presence = dict.fromkeys(sums, False)
    has_data = False

    def _accumulate(usage_obj: dict[str, Any], *, replace: bool) -> bool:
        nonlocal has_data
        input_tokens, output_tokens, cache_creation, cache_read, has_known_key = _bucket_from_usage(usage_obj)
        if not has_known_key:
            return False
        for key, value in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
            ("cache_creation_tokens", cache_creation),
            ("cache_read_tokens", cache_read),
        ):
            if value is not None:
                sums[key] = value if replace else sums[key] + value
                bucket_presence[key] = True
        has_data = True
        return True

    # Path 1 (preferred): walk every message in messages[] and accumulate.
    for candidate_payload in payload_candidates:
        msgs = candidate_payload.get("messages")
        if not isinstance(msgs, list) or not msgs:
            continue
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            usage_obj: dict[str, Any] | None = None
            for key in ("usage_metadata", "usage"):
                value = msg.get(key)
                if isinstance(value, dict) and value:
                    usage_obj = value
                    break
            if usage_obj is None:
                response_metadata = msg.get("response_metadata")
                if isinstance(response_metadata, dict):
                    token_usage = response_metadata.get("token_usage")
                    if isinstance(token_usage, dict) and token_usage:
                        usage_obj = token_usage
            if usage_obj:
                _accumulate(usage_obj, replace=False)
        if has_data:
            break

    # Path 2 (fallback): flat top-level ``usage``/``usage_metadata``.
    if not has_data:
        for candidate_payload in payload_candidates:
            for key in ("usage", "usage_metadata"):
                usage_obj = candidate_payload.get(key)
                if isinstance(usage_obj, dict) and usage_obj and _accumulate(usage_obj, replace=True):
                    break
            if has_data:
                break

    if not has_data:
        return zero

    present = {key: sums[key] if bucket_presence[key] else None for key in sums}
    components = [value for value in present.values() if value is not None]
    out: TokenMetrics = {
        "prompt_tokens": present["input_tokens"],
        "completion_tokens": present["output_tokens"],
        "total_tokens": sum(components) if components else None,
        "cache_creation_tokens": present["cache_creation_tokens"],
        "cache_read_tokens": present["cache_read_tokens"],
        "duration_ms": None,
    }
    for candidate_payload in payload_candidates:
        duration_ms = candidate_payload.get("duration_ms")
        if isinstance(duration_ms, int | float) and out["duration_ms"] is None:
            out["duration_ms"] = float(duration_ms)
    return out


__all__ = ["TokenMetrics", "agent_log_has_workflow_error", "extract_usage_metrics", "iter_agent_log_json_payloads"]
