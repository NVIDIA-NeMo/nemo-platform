# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Derive factual trace structure without assigning an outcome or cause."""

from collections import Counter
from datetime import datetime
from typing import Any, Optional

# A provider traceback can repeat verbatim across every retry, so the overview keeps
# only enough to identify the failure. The trace payload keeps the full text.
MAX_ERROR_MESSAGE = 600


def _values(rows: list[dict[str, Any]], field: str) -> list[str]:
    return sorted({str(row[field]) for row in rows if row.get(field) not in {None, ""}})


def _counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[field]) for row in rows if row.get(field) not in {None, ""}).items()))


def _timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_ms(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    try:
        return max(0.0, (end - start).total_seconds() * 1000)
    except TypeError:
        return None


def _trace_duration_ms(spans: list[dict[str, Any]]) -> Optional[float]:
    starts = [_timestamp(span.get("started_at")) for span in spans]
    ends = [_timestamp(span.get("ended_at")) for span in spans]
    valid_starts = [value for value in starts if value is not None]
    valid_ends = [value for value in ends if value is not None]
    try:
        return _duration_ms(min(valid_starts), max(valid_ends)) if valid_starts and valid_ends else None
    except TypeError:
        return None


def _error_span(span: dict[str, Any]) -> dict[str, Any]:
    """Identify one error span without carrying its whole traceback."""
    entry: dict[str, Any] = {
        field: span[field]
        for field in ("span_id", "parent_span_id", "name", "kind", "error_type")
        if span.get(field) is not None
    }
    message = span.get("error_message")
    if message is None:
        return entry
    text = message if isinstance(message, str) else str(message)
    entry["error_message"] = text[:MAX_ERROR_MESSAGE]
    if len(text) > MAX_ERROR_MESSAGE:
        entry["error_message_truncated"] = True
        entry["error_message_length"] = len(text)
    return entry


def build_timeline(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Place every span in order with its offset from the first start and its duration.

    This is kept beside the overview rather than inside it, because a long trace
    would otherwise bloat the report front matter that copies the overview.
    """
    paired = [(span, _timestamp(span.get("started_at"))) for span in bundle.get("spans", []) if isinstance(span, dict)]
    valid_starts = [start for _, start in paired if start is not None]
    try:
        origin = min(valid_starts) if valid_starts else None
    except TypeError:
        origin = None
    return [
        {
            "span_id": span.get("span_id"),
            "parent_span_id": span.get("parent_span_id"),
            "name": span.get("name"),
            "kind": span.get("kind"),
            "status": span.get("status"),
            "offset_ms": _duration_ms(origin, start),
            "duration_ms": _duration_ms(start, _timestamp(span.get("ended_at"))),
        }
        for span, start in paired
    ]


def _evaluator_signal(result: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "evaluator_result_id",
        "span_id",
        "session_id",
        "name",
        "data_type",
        "value",
        "string_value",
        "comment",
        "created_at",
    )
    return {field: result[field] for field in fields if result.get(field) is not None}


def build_overview(bundle: dict[str, Any]) -> dict[str, Any]:
    """Summarize observable trace structure for a later evidence-based assessment."""
    spans = [span for span in bundle.get("spans", []) if isinstance(span, dict)]
    raw_summary = bundle.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    evaluator_results = [result for result in bundle.get("evaluator_results", []) if isinstance(result, dict)]
    errors = [span for span in spans if span.get("status") == "error"]
    error_spans = [_error_span(span) for span in errors]
    root_status = summary.get("status", "unknown")
    duration_ms = summary.get("duration_ms")
    if duration_ms is None and spans:
        duration_ms = _trace_duration_ms(spans)

    agents = set(_values(spans, "agent_name"))
    if summary.get("agent_name"):
        agents.add(str(summary["agent_name"]))
    models = set(_values(spans, "model"))
    models.update(str(value) for value in (summary.get("models") or []) if value)
    providers = set(_values(spans, "provider"))
    providers.update(str(value) for value in (summary.get("providers") or []) if value)
    sessions = sorted(
        {str(value) for value in bundle.get("session_ids", []) if value}
        | {str(span["session_id"]) for span in spans if span.get("session_id")}
    )
    return {
        "trace_id": bundle.get("trace_id"),
        "trace_ref": bundle.get("trace_ref"),
        "root_status": root_status,
        "root_duration_ms": duration_ms,
        "span_count": len(spans),
        "session_count": len(sessions),
        "session_ids": sessions,
        "status_counts": _counts(spans, "status"),
        "kind_counts": _counts(spans, "kind"),
        "tools": _values(spans, "tool_name"),
        "models": sorted(models),
        "providers": sorted(providers),
        "agents": sorted(agents),
        "sources": _values(spans, "source"),
        "projects": _values(spans, "project"),
        "error_span_count": len(errors),
        "error_spans": error_spans,
        "root_succeeded_with_errors": root_status == "success" and bool(errors),
        "cancelled_span_ids": [span.get("span_id") for span in spans if span.get("status") == "cancelled"],
        "incomplete_span_ids": [
            span.get("span_id")
            for span in spans
            if span.get("status") in {None, "unknown"} or span.get("ended_at") is None
        ],
        "evaluator_result_count": len(evaluator_results),
        "evaluator_signals": [_evaluator_signal(result) for result in evaluator_results],
    }
