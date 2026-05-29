# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parsing the stream-json result line into a ResultEvent."""

import json
from datetime import datetime, timezone
from pathlib import Path

from coding_agents.events import ResultEvent


def to_result_event(raw: dict, *, session_id: str, artifact_dir: Path) -> ResultEvent:
    """Translate a single stream-json `result` event dict into a ResultEvent.

    Claude Code can emit subtype="success" *and* is_error=true on the same
    line; `success` reflects both — a "successful" result that's also an
    error becomes success=False.
    """
    subtype = str(raw.get("subtype", ""))
    is_error = bool(raw.get("is_error", False))
    return ResultEvent(
        session_id=session_id,
        artifact_dir=artifact_dir,
        success=(subtype == "success" and not is_error),
        text=raw.get("result"),
        cost_usd=float(raw.get("total_cost_usd") or 0.0),
        duration_ms=float(raw.get("duration_ms") or 0.0),
        num_turns=int(raw.get("num_turns") or 0),
        stop_reason=str(raw.get("stop_reason", "")),
        timestamp=datetime.now(timezone.utc),
    )


def find_result_in_jsonl(jsonl_path: Path) -> dict | None:
    """Scan a stream-json file for the (single) `result` event line.

    Returns None if the file is missing or contains no result line.
    Malformed lines are skipped — Claude Code occasionally emits non-JSON
    output to stdout before the stream starts.
    """
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # A valid JSON line might still be a list/number/string; skip
                # those so the .get() below is always safe.
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "result":
                    return event
    except FileNotFoundError:
        return None
    return None
