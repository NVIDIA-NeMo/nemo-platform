# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""JSON-returning Intake span and trace queries."""

from datetime import datetime
from typing import Any, Optional, Union

from sources.intake._http import IntakeClient

DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 1000
DEFAULT_TRACE_LIMIT = 50
MAX_TRACE_LIMIT = 200
_MAX_PAGE_SIZE = 100
_TRACE_ID_CHUNK = 50


def _limit(value: int, maximum: int) -> int:
    return max(1, min(value, maximum))


def _page_size(limit: int) -> int:
    return max(1, min(limit, _MAX_PAGE_SIZE))


def trace_ref(trace_id: str) -> str:
    """Build the one canonical Intake trace reference that every caller emits."""
    return f"intake://traces/{trace_id}"


def _since_filter(since: Optional[Union[datetime, str]]) -> Optional[dict[str, Any]]:
    if since is None:
        return None
    return {"gte": since.isoformat() if isinstance(since, datetime) else since}


def group_spans(
    client: IntakeClient,
    *,
    by: str,
    filter: Optional[dict[str, Any]] = None,
    sort: Optional[str] = None,
    limit: int = DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    """Roll spans up by one field, so a search can rank whole traces rather than spans."""
    limit = _limit(limit, MAX_ROW_LIMIT)
    rows, truncated = client.drain(
        "spans/groups",
        {"filter": filter, "sort": sort or "-started_at", "by": by, "page_size": _page_size(limit)},
        limit=limit,
    )
    return {"groups": rows, "count": len(rows), "truncated": truncated}


def query_traces(
    client: IntakeClient,
    *,
    filter: Optional[dict[str, Any]] = None,
    sort: Optional[str] = None,
    mode: str = "preview",
    limit: int = DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    """Query Intake trace summaries and server-computed rollups."""
    limit = _limit(limit, MAX_ROW_LIMIT)
    rows, truncated = client.drain(
        "traces",
        {
            "filter": filter,
            "sort": sort or "-started_at",
            "mode": mode,
            "page_size": _page_size(limit),
        },
        limit=limit,
    )
    return {"traces": rows, "count": len(rows), "truncated": truncated}


def recent_traces(
    client: IntakeClient,
    *,
    since: Optional[Union[datetime, str]] = None,
    limit: int = DEFAULT_TRACE_LIMIT,
) -> dict[str, Any]:
    """List the most recent traces in one workspace, newest first."""
    limit = _limit(limit, MAX_TRACE_LIMIT)
    started_at = _since_filter(since)
    page = query_traces(
        client,
        filter={"started_at": started_at} if started_at else None,
        sort="-started_at",
        mode="preview",
        limit=limit,
    )
    traces = [_trace_entry(row["id"], row) for row in page["traces"] if row.get("id")]
    result: dict[str, Any] = {
        "traces": traces,
        "count": len(traces),
        "truncated": page["truncated"],
    }
    if not traces:
        window = f" since {started_at['gte']}" if started_at else ""
        result["note"] = (
            f"No traces were recorded in workspace '{client.workspace}'{window}. "
            "An empty result is not an error. Confirm the workspace and that the agent reports to Intake."
        )
    return result


def find_agent_traces(
    client: IntakeClient,
    agent: str,
    *,
    since: Optional[Union[datetime, str]] = None,
    limit: int = DEFAULT_TRACE_LIMIT,
) -> dict[str, Any]:
    """Find recent traces that contain a span from one agent."""
    limit = _limit(limit, MAX_TRACE_LIMIT)
    span_filter: dict[str, Any] = {"agent_name": agent}
    started_at = _since_filter(since)
    if started_at is not None:
        span_filter["started_at"] = started_at

    grouped = group_spans(
        client,
        by="trace_id",
        filter=span_filter,
        sort="-started_at",
        limit=limit,
    )
    ordered = [
        group["group"]["trace_id"]
        for group in grouped["groups"]
        if isinstance(group.get("group"), dict) and group["group"].get("trace_id")
    ]

    summaries: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ordered), _TRACE_ID_CHUNK):
        chunk = ordered[start : start + _TRACE_ID_CHUNK]
        page = query_traces(
            client,
            filter={"id": {"$in": chunk}},
            sort="-started_at",
            mode="preview",
            limit=len(chunk),
        )
        summaries.update({row["id"]: row for row in page["traces"] if row.get("id")})

    traces = [_trace_entry(trace_id, summaries.get(trace_id)) for trace_id in ordered]
    traces.sort(key=lambda entry: entry["started_at"] or "", reverse=True)
    result: dict[str, Any] = {
        "traces": traces,
        "count": len(traces),
        "truncated": grouped["truncated"],
    }
    if not traces:
        window = f" since {started_at['gte']}" if started_at else ""
        result["note"] = (
            f"No spans matched agent_name='{agent}' in workspace '{client.workspace}'{window}. "
            "An empty result is not an error. Confirm the agent_name value reported to Intake."
        )
    return result


def _trace_entry(trace_id: str, summary: Optional[dict[str, Any]]) -> dict[str, Any]:
    summary = summary or {}
    return {
        "trace_ref": trace_ref(trace_id),
        "trace_id": trace_id,
        "started_at": summary.get("started_at"),
        "status": summary.get("status", "unknown"),
        "span_count": summary.get("span_count"),
        "error_count": summary.get("error_count"),
        "duration_ms": summary.get("duration_ms"),
        "name": summary.get("name"),
    }
