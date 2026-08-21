# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load one complete Intake trace as a lossless JSON analysis bundle."""

from typing import Any

from _http import IntakeClient, IntakeError
from traces import query_traces


def _trace_id(ref: str) -> str:
    trace_id = ref.removeprefix("intake://").removeprefix("traces/")
    if not trace_id:
        raise ValueError("trace reference must include a trace ID.")
    return trace_id


def read_trace(client: IntakeClient, ref: str) -> dict[str, Any]:
    """Fetch a trace summary, every detailed span, and related evaluator results."""
    trace_id = _trace_id(ref)
    summary_page = query_traces(
        client,
        filter={"id": {"$in": [trace_id]}},
        mode="detailed",
        limit=1,
    )
    summary = next((row for row in summary_page["traces"] if row.get("id") == trace_id), None)

    spans, _ = client.drain(
        "spans",
        {
            "filter": {"trace_id": trace_id},
            "sort": "started_at",
            "mode": "detailed",
            "page_size": 100,
        },
        limit=None,
    )
    if not spans:
        raise IntakeError(
            f"No spans matched trace '{trace_id}' in workspace '{client.workspace}'. "
            "Confirm the trace ID and workspace."
        )
    spans.sort(key=lambda span: (span.get("started_at") or "", span.get("span_id") or ""))

    span_ids = {span["span_id"] for span in spans if span.get("span_id")}
    session_ids = sorted({span["session_id"] for span in spans if span.get("session_id")})
    evaluator_results: list[dict[str, Any]] = []
    for session_id in session_ids:
        rows, _ = client.drain(
            "evaluator-results",
            {
                "filter": {"session_id": session_id},
                "sort": "created_at",
                "page_size": 100,
            },
            limit=None,
        )
        evaluator_results.extend(row for row in rows if row.get("span_id") in span_ids)
    evaluator_results.sort(key=lambda result: (result.get("created_at") or "", result.get("evaluator_result_id") or ""))

    return {
        "trace_ref": f"intake://{trace_id}",
        "trace_id": trace_id,
        "summary": summary,
        "session_ids": session_ids,
        "spans": spans,
        "evaluator_results": evaluator_results,
    }
