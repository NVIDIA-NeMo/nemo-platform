# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read an Intake trace in two passes: cheap structure first, span payloads on request.

Intake serves spans in two modes. ``summary`` carries every structural field an
overview needs; ``detailed`` adds ``input``, ``output``, and ``raw_attributes``, which
measured 82x larger on a real trace. Reading structure in ``summary`` mode keeps the
first look affordable, so ``detailed`` is only ever spent on spans the caller names.
"""

import json
from collections.abc import Callable, Sequence
from typing import Any, Optional

from sources.intake._http import IntakeClient, IntakeError
from sources.intake.traces import query_traces, trace_ref

PAGE_SIZE = 100
DEFAULT_SPAN_LIMIT = 20
DEFAULT_MAX_CHARS = 2000

# Only these three fields are absent from summary mode, so only these need bounding.
PAYLOAD_FIELDS = ("input", "output", "raw_attributes")


def _trace_id(ref: str) -> str:
    trace_id = ref.removeprefix("intake://").removeprefix("traces/")
    if not trace_id:
        raise ValueError("trace reference must include a trace ID.")
    return trace_id


def _sorted_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spans.sort(key=lambda span: (span.get("started_at") or "", span.get("span_id") or ""))
    return spans


def _evaluator_results(client: IntakeClient, spans: Sequence[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Join evaluator results onto a trace through the sessions its spans belong to.

    Evaluator results are not addressable by trace. They hang off a session, and one
    session can outlive the trace, so the rows have to be filtered back down to the
    spans this trace actually contains.
    """
    span_ids = {span["span_id"] for span in spans if span.get("span_id")}
    session_ids = sorted({span["session_id"] for span in spans if span.get("session_id")})
    results: list[dict[str, Any]] = []
    for session_id in session_ids:
        rows, _ = client.drain(
            "evaluator-results",
            {"filter": {"session_id": session_id}, "sort": "created_at", "page_size": PAGE_SIZE},
            limit=None,
        )
        results.extend(row for row in rows if row.get("span_id") in span_ids)
    results.sort(key=lambda result: (result.get("created_at") or "", result.get("evaluator_result_id") or ""))
    return session_ids, results


def read_overview(client: IntakeClient, ref: str) -> dict[str, Any]:
    """Fetch the trace summary, every span in summary mode, and its evaluator results."""
    trace_id = _trace_id(ref)
    summary_page = query_traces(client, filter={"id": {"$in": [trace_id]}}, mode="detailed", limit=1)
    summary = next((row for row in summary_page["traces"] if row.get("id") == trace_id), None)

    spans, _ = client.drain(
        "spans",
        {"filter": {"trace_id": trace_id}, "sort": "started_at", "mode": "summary", "page_size": PAGE_SIZE},
        limit=None,
    )
    if not spans:
        raise IntakeError(
            f"No spans matched trace '{trace_id}' in workspace '{client.workspace}'. "
            "Confirm the trace ID and workspace."
        )
    spans = _sorted_spans(spans)
    session_ids, evaluator_results = _evaluator_results(client, spans)
    return {
        "trace_ref": trace_ref(trace_id),
        "trace_id": trace_id,
        "summary": summary,
        "session_ids": session_ids,
        "spans": spans,
        "evaluator_results": evaluator_results,
    }


def _bounded(span: dict[str, Any], max_chars: Optional[int]) -> dict[str, Any]:
    """Cap the payload fields, recording the full length of anything shortened.

    A shortened field becomes the leading JSON text of the original value rather than
    the value itself. That keeps one predictable rule for objects and strings alike,
    and the recorded length tells the caller when to ask for the field in full.
    """
    if max_chars is None:
        return span
    bounded = dict(span)
    for field in PAYLOAD_FIELDS:
        value = bounded.get(field)
        if value is None:
            continue
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        if len(text) <= max_chars:
            continue
        bounded[field] = text[:max_chars]
        bounded[field + "_truncated"] = True
        bounded[field + "_length"] = len(text)
    return bounded


def read_spans(
    client: IntakeClient,
    ref: str,
    *,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    span_ids: Sequence[str] = (),
    limit: int = DEFAULT_SPAN_LIMIT,
    max_chars: Optional[int] = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Fetch detailed payloads for a named slice of one trace's spans.

    Intake accepts neither ``$eq`` nor ``$in`` on a span ``id``, so an explicit
    ``span_ids`` selection is applied here rather than server-side. Pairing it with
    ``status`` or ``kind`` narrows the fetch before it reaches this filter.
    """
    trace_id = _trace_id(ref)
    query: dict[str, Any] = {"trace_id": trace_id}
    if status:
        query["status"] = status
    if kind:
        query["kind"] = kind
    if parent_span_id:
        query["parent_span_id"] = parent_span_id

    wanted = list(dict.fromkeys(span_ids))
    stop_when: Optional[Callable[[list[dict[str, Any]]], bool]] = None
    if wanted:
        remaining = set(wanted)

        def stop_when(rows: list[dict[str, Any]]) -> bool:
            remaining.difference_update(row.get("span_id") for row in rows)
            return not remaining

    rows, truncated = client.drain(
        "spans",
        {"filter": query, "sort": "started_at", "mode": "detailed", "page_size": PAGE_SIZE},
        limit=None if wanted else limit,
        stop_when=stop_when,
    )
    if wanted:
        by_id = {row.get("span_id"): row for row in rows}
        selected = [by_id[span_id] for span_id in wanted if span_id in by_id]
        missing = [span_id for span_id in wanted if span_id not in by_id]
        truncated = False
    else:
        selected = _sorted_spans(rows)
        missing = []

    result: dict[str, Any] = {
        "trace_ref": trace_ref(trace_id),
        "trace_id": trace_id,
        "selection": {
            key: value
            for key, value in (
                ("status", status),
                ("kind", kind),
                ("parent_span_id", parent_span_id),
                ("span_ids", wanted or None),
            )
            if value is not None
        },
        # Always reported, because null is the difference between "payloads are whole"
        # and "payloads were shortened", and a caller quoting evidence needs to know.
        "max_chars": max_chars,
        "spans": [_bounded(span, max_chars) for span in selected],
        "count": len(selected),
        "truncated": truncated,
    }
    if missing:
        result["missing_span_ids"] = missing
    if not selected:
        result["note"] = (
            f"No spans in trace '{trace_id}' matched this selection. An empty result is not an error. "
            "Read the overview to see which span IDs, kinds, and statuses the trace contains."
        )
    return result
