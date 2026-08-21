# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Provider-neutral Analyst tools for discovering and hydrating traces."""

from collections.abc import AsyncIterator
from datetime import datetime, timezone

from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_platform_plugin.trace_provider import TraceQuery, TraceRef


def _parse_datetime(value: str | None, *, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _later_datetime(first: datetime | None, second: datetime | None) -> datetime | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


async def filter_traces(
    deps: AnalystDeps,
    *,
    trace_ids: list[str] | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
    has_error: bool | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """List lightweight trace references through the configured provider."""
    if deps.trace_provider is None:
        raise RuntimeError("analyst trace provider is not configured")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    requested_limit = min(limit, deps.max_results)
    lower_bound = _later_datetime(
        _parse_datetime(started_after, field="started_after"),
        deps.since,
    )
    query = TraceQuery(
        ids=tuple(trace_ids or ()),
        started_after=lower_bound,
        started_before=_parse_datetime(started_before, field="started_before"),
        has_error=has_error,
        limit=requested_limit + 1,
    )
    refs: list[TraceRef] = []
    async for ref in deps.trace_provider.filter_traces(query):
        refs.append(ref)
        if len(refs) > requested_limit:
            break
    truncated = len(refs) > requested_limit
    refs = refs[:requested_limit]
    return {
        "provider": deps.trace_provider.name,
        "traces": [{"id": ref.id, "summary": ref.summary} for ref in refs],
        "count": len(refs),
        "truncated": truncated,
    }


async def read_traces(deps: AnalystDeps, *, trace_ids: list[str]) -> dict[str, object]:
    """Hydrate provider-native trace rows for the requested ids."""
    if deps.trace_provider is None:
        raise RuntimeError("analyst trace provider is not configured")
    unique_ids = list(dict.fromkeys(trace_ids))
    if not unique_ids:
        raise ValueError("trace_ids must contain at least one id")
    if len(unique_ids) > deps.max_results:
        raise ValueError(f"cannot read more than {deps.max_results} traces at once")

    async def refs() -> AsyncIterator[TraceRef]:
        for trace_id in unique_ids:
            yield TraceRef(id=trace_id)

    rows = [{"id": row.id, "data": row.data} async for row in deps.trace_provider.read_traces(refs())]
    return {
        "provider": deps.trace_provider.name,
        "traces": rows,
        "count": len(rows),
    }
