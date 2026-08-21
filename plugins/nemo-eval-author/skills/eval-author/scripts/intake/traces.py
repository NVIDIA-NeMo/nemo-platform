# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""JSON-returning Intake span and trace queries."""

from datetime import datetime
from typing import Any

from _http import IntakeClient

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


def _with_trace_ref(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    group = result.get("group")
    trace_id = result.get("trace_id") or (group.get("trace_id") if isinstance(group, dict) else None)
    if trace_id:
        result["trace_ref"] = f"intake://{trace_id}"
    return result


def query_spans(
    client: IntakeClient,
    *,
    filter: dict[str, Any] | None = None,
    group_by: str | None = None,
    sort: str | None = None,
    mode: str = "summary",
    limit: int = DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    """Query Intake spans, either flat or grouped."""
    limit = _limit(limit, MAX_ROW_LIMIT)
    params: dict[str, Any] = {
        "filter": filter,
        "sort": sort or "-started_at",
        "page_size": _page_size(limit),
    }
    if group_by is not None:
        params["by"] = group_by
        rows, truncated = client.drain("spans/groups", params, limit=limit)
        groups = [_with_trace_ref(row) for row in rows]
        return {
            "groups": groups,
            "grouped_by": group_by,
            "count": len(groups),
            "truncated": truncated,
        }

    params["mode"] = mode
    rows, truncated = client.drain("spans", params, limit=limit)
    spans = [_with_trace_ref(row) for row in rows]
    return {"spans": spans, "count": len(spans), "truncated": truncated}


def query_traces(
    client: IntakeClient,
    *,
    filter: dict[str, Any] | None = None,
    sort: str | None = None,
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


def find_agent_traces(
    client: IntakeClient,
    agent: str,
    *,
    since: datetime | str | None = None,
    limit: int = DEFAULT_TRACE_LIMIT,
) -> dict[str, Any]:
    """Find recent traces that contain a span from one agent."""
    limit = _limit(limit, MAX_TRACE_LIMIT)
    span_filter: dict[str, Any] = {"agent_name": agent}
    if since is not None:
        span_filter["started_at"] = {"gte": since.isoformat() if isinstance(since, datetime) else since}

    grouped = query_spans(
        client,
        filter=span_filter,
        group_by="trace_id",
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
        window = f" since {span_filter['started_at']['gte']}" if since is not None else ""
        result["note"] = (
            f"No spans matched agent_name='{agent}' in workspace '{client.workspace}'{window}. "
            "An empty result is not an error. Confirm the agent_name value reported to Intake."
        )
    return result


def _trace_entry(trace_id: str, summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = summary or {}
    return {
        "trace_ref": f"intake://{trace_id}",
        "trace_id": trace_id,
        "started_at": summary.get("started_at"),
        "status": summary.get("status", "unknown"),
        "span_count": summary.get("span_count"),
        "error_count": summary.get("error_count"),
        "duration_ms": summary.get("duration_ms"),
        "name": summary.get("name"),
    }
