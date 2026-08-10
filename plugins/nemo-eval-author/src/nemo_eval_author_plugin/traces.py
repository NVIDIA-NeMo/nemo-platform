# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Intake trace querying for standalone Eval Author.

Eval Author must find the production traces of an agent under test, slice that
population to decide what is worth reading, then read one trace in full.

Intake has no endpoint for the first step. Only spans carry ``agent_name``, so
``traces.list`` cannot be scoped to an agent, and ``spans.groups.list`` sorts
only by span count. ``list_traces`` therefore works in two steps. It walks one
newest-first span stream to collect the distinct trace ids of the agent, then
asks ``traces.list`` for the summary of exactly those ids. The second step
matters: a span scan sees only its own window, so counts taken from it are
lower bounds, while ``traces.list`` returns the counts that the server holds.

Reading and diagnosis are not rebuilt here. ``read_trace`` delegates to
``TraceExplorer`` and ``analyze_trace`` delegates to ``TraceAnalyzer``.

Failure-mode discovery stays with the Analyst. ``facets`` counts exact field
values so that a caller can choose what to read. It does not cluster.
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from nemo_experimentalist_plugin.entities import ResourceRef, Task, TrialResult
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import Diagnostic, TraceAnalyzer
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import TraceExplorer
from nemo_platform import APIConnectionError, APIStatusError, AsyncNeMoPlatform

DEFAULT_TRACE_LIMIT = 50
MAX_TRACE_LIMIT = 200
DEFAULT_SPAN_BUDGET = 1000
_MAX_PAGE_SIZE = 100
# Trace ids travel in the query string, so one wide ``$in`` can overrun the URL limit
# of the server. At 50 ids the query stays near 2 KB.
_TRACE_ID_CHUNK = 50

# Facet name -> the ``Span`` attribute it reads. Intake groups server-side only by
# trace_id and session_id, so every other cut is counted client-side.
_FACETS = {"error_type": "error_type", "tool": "tool_name", "model": "model"}


class TraceQueryError(RuntimeError):
    """An Intake read failed. The message names the next thing to try."""


def _explain(exc: Exception, *, doing: str, workspace: str) -> TraceQueryError:
    """Turn an SDK failure into an error that names a corrective action."""
    if isinstance(exc, APIStatusError):
        if exc.status_code in (401, 403):
            hint = (
                "Credentials were rejected. Run `nemo auth login`, then confirm that NMP_BASE_URL "
                f"points at the cluster that owns workspace '{workspace}'."
            )
        elif exc.status_code == 404:
            hint = f"Intake returned 404. Confirm that workspace '{workspace}' exists and that the trace id is correct."
        else:
            hint = f"Intake returned HTTP {exc.status_code}: {exc}"
        return TraceQueryError(f"{doing} failed. {hint}")
    if isinstance(exc, APIConnectionError):
        return TraceQueryError(
            f"{doing} failed: the platform is unreachable. Check NMP_BASE_URL and that the services run."
        )
    if isinstance(exc, ValueError):
        # TraceExplorer raises ValueError both for an unreadable ref and for a trace with
        # no spans. Its message is specific; only the workspace is missing from it.
        return TraceQueryError(
            f"{doing} failed in workspace '{workspace}': {exc}. Confirm the trace id, and that "
            "this workspace is the one the trace was ingested into."
        )
    return TraceQueryError(f"{doing} failed: {type(exc).__name__}: {exc}")


async def _scan_agent_spans(
    client: AsyncNeMoPlatform,
    *,
    agent: str,
    workspace: str,
    since: datetime | None,
    limit: int,
    span_budget: int,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Collect the distinct traces of one agent by walking spans newest first.

    Only spans carry ``agent_name``, which is the reason this scan exists. It also
    collects the facet values, because Intake groups server-side only by trace_id
    and session_id.

    Returns:
        The traces in encounter order, and a flag for whether the scan stopped early.
    """
    span_filter: dict[str, Any] = {"agent_name": agent}
    if since is not None:
        span_filter["started_at"] = {"gte": since.isoformat()}

    found: dict[str, dict[str, Any]] = {}
    trace: dict[str, Any] | None
    truncated = False
    scanned = 0
    paginator = client.intake.spans.list(
        workspace=workspace,
        filter=cast(Any, span_filter),
        sort="-started_at",
        mode="summary",
        page_size=max(1, min(span_budget, _MAX_PAGE_SIZE)),
    )
    try:
        async for span in paginator:
            if scanned >= span_budget:
                truncated = True
                break
            scanned += 1
            trace_id = span.trace_id
            if not trace_id:
                continue
            trace = found.get(trace_id)
            if trace is None:
                if len(found) >= limit:
                    truncated = True
                    break
                # Every field here is a fallback for a trace that traces.list does not
                # return, which happens when the root span of the trace was never ingested.
                trace = {
                    "trace_ref": f"intake://{trace_id}",
                    "started_at": span.started_at.isoformat(),
                    "status": "unknown",
                    "span_count": None,
                    "error_count": None,
                    "duration_ms": None,
                    "name": None,
                    **{facet: set() for facet in _FACETS},
                }
                found[trace_id] = trace
            # Spans arrive newest first, so the last one seen for a trace is its oldest,
            # which is the closest this scan can get to the start time of the trace.
            trace["started_at"] = span.started_at.isoformat()
            for facet, attribute in _FACETS.items():
                value = getattr(span, attribute, None)
                if value:
                    trace[facet].add(str(value))
    except Exception as exc:
        raise _explain(exc, doing=f"Listing traces for agent '{agent}'", workspace=workspace) from exc
    return found, truncated


async def _merge_trace_summaries(
    client: AsyncNeMoPlatform,
    found: dict[str, dict[str, Any]],
    *,
    workspace: str,
) -> None:
    """Replace the scanned fields of each trace with the server-computed summary.

    The span scan sees only its own window, so any count taken from it is a lower
    bound. ``traces.list`` returns the real status, span count, and error count.
    """
    ids = list(found)
    try:
        for start in range(0, len(ids), _TRACE_ID_CHUNK):
            chunk = ids[start : start + _TRACE_ID_CHUNK]
            paginator = client.intake.traces.list(
                workspace=workspace,
                filter=cast(Any, {"id": {"$in": chunk}}),
                sort="-started_at",
                # preview is the cheapest mode that carries the rollups. Its payload
                # previews are read off the wire and dropped.
                mode="preview",
                page_size=len(chunk),
            )
            async for summary in paginator:
                trace = found.get(summary.id)
                if trace is None:
                    continue
                trace["started_at"] = summary.started_at.isoformat()
                trace["status"] = summary.status
                trace["span_count"] = summary.span_count
                trace["error_count"] = summary.error_count
                trace["duration_ms"] = summary.duration_ms
                trace["name"] = summary.name
    except Exception as exc:
        raise _explain(exc, doing="Reading trace summaries", workspace=workspace) from exc


async def list_traces(
    client: AsyncNeMoPlatform,
    *,
    agent: str,
    workspace: str,
    since: datetime | None = None,
    limit: int = DEFAULT_TRACE_LIMIT,
    span_budget: int = DEFAULT_SPAN_BUDGET,
) -> dict[str, Any]:
    """List the most recent traces of one agent, newest first.

    Args:
        client: Platform client.
        agent: Value that the agent reports to Intake as ``agent_name``.
        workspace: Workspace to search.
        since: Optional lower bound on span start time.
        limit: Maximum number of traces to return. Clamped to ``MAX_TRACE_LIMIT``.
        span_budget: Maximum number of spans to read. Stops one wide query from
            flooding the caller's context.

    Returns:
        ``{"traces": [...], "count": int, "truncated": bool}``, and a ``note`` key
        when no trace matched. ``truncated`` is True when the limit or the span
        budget stopped the scan, so more traces exist than the ones returned.

        Each trace carries ``trace_ref``, ``started_at``, ``status``, ``span_count``,
        ``error_count``, ``duration_ms``, ``name``, and one sorted list per facet.
        Every field except the facets comes from the server and is exact.

    Raises:
        TraceQueryError: The Intake read failed.
    """
    limit = max(1, min(limit, MAX_TRACE_LIMIT))
    found, truncated = await _scan_agent_spans(
        client,
        agent=agent,
        workspace=workspace,
        since=since,
        limit=limit,
        span_budget=span_budget,
    )
    if found:
        await _merge_trace_summaries(client, found, workspace=workspace)

    traces = sorted(found.values(), key=lambda entry: entry["started_at"], reverse=True)
    for entry in traces:
        for facet in _FACETS:
            entry[facet] = sorted(entry[facet])

    result: dict[str, Any] = {"traces": traces, "count": len(traces), "truncated": truncated}
    if not traces:
        window = f" since {since.isoformat()}" if since is not None else ""
        result["note"] = (
            f"No spans matched agent_name='{agent}' in workspace '{workspace}'{window}. "
            "An empty result is not an error. Check the agent name against the value that the "
            "agent reports to Intake, because a wrong name is the usual cause."
        )
    return result


def facets(result: dict[str, Any], by: str) -> dict[str, int]:
    """Count the traces of a ``list_traces`` result per distinct value of ``by``.

    Args:
        result: A ``list_traces`` return value.
        by: ``"status"``, or one of ``"error_type"``, ``"tool"``, ``"model"``. A trace
            that holds two values of a field counts once against each.

    Returns:
        Value to trace count, largest count first.

    Raises:
        ValueError: ``by`` is not a supported facet.
    """
    traces = result["traces"]
    if by == "status":
        counts = Counter(trace["status"] for trace in traces)
    elif by in _FACETS:
        # ponytail: the facet values come from the scanned span window, so a trace can
        # hold a tool or model that this count misses. Raise span_budget to see more.
        counts = Counter(value for trace in traces for value in trace[by])
    else:
        raise ValueError(f"Unsupported facet '{by}'. Use 'status', {', '.join(repr(name) for name in _FACETS)}.")
    return dict(counts.most_common())


async def read_trace(client: AsyncNeMoPlatform, ref: str, *, workspace: str) -> TraceExplorer:
    """Read one production trace in full.

    Args:
        client: Platform client.
        ref: A bare trace id, ``intake://<id>``, or ``intake://traces/<id>``. The first
            two are what ``list_traces`` and ``Insight.trace_refs`` produce.
        workspace: Workspace that holds the trace.

    Returns:
        A loaded ``TraceExplorer``.

    Raises:
        TraceQueryError: The trace is missing or unreadable.
    """
    uri = ref if ref.startswith("intake://") else f"intake://{ref}"
    try:
        return await TraceExplorer.from_ref(ResourceRef(uri=uri), client, workspace)
    except Exception as exc:
        raise _explain(exc, doing=f"Reading trace '{ref}'", workspace=workspace) from exc


async def analyze_trace(
    client: AsyncNeMoPlatform,
    ref: str,
    *,
    workspace: str,
    experiment_dir: Path,
    agent_path: Path,
) -> Diagnostic:
    """Diagnose one production trace with the Experimentalist trace analyzer.

    ``TraceAnalyzer.run`` expects an evaluator trial. A production trace has none, so
    this function synthesizes the ``Task`` and ``TrialResult`` around the trace ref.
    The task declares no dependencies, so ``Task.start_deps()`` starts nothing.

    Args:
        client: Platform client.
        ref: A bare trace id, ``intake://<id>``, or ``intake://traces/<id>``.
        workspace: Workspace that holds the trace.
        experiment_dir: Directory for analyzer artifacts.
        agent_path: Local path to the source of the agent under test.

    Returns:
        The diagnosis: outcome, summary, failure point, and root cause.
    """
    trace_id = ref.removeprefix("intake://").removeprefix("traces/")
    task = Task(id=f"trace-{trace_id}", description="Production trace with no evaluator task behind it.")
    trial = TrialResult(
        id=f"trace-{trace_id}",
        task_id=task.id,
        status="completed",
        trace=ResourceRef(uri=f"intake://{trace_id}", description="Production trace read from Intake."),
        metadata={"source": "intake"},
    )
    return await TraceAnalyzer(experiment_dir=experiment_dir).run(
        trial=trial,
        task=task,
        agent_path=agent_path,
        insight=None,
        client=client,
        workspace=workspace,
    )
