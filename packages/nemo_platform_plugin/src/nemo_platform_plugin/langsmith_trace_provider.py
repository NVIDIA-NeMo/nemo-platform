# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace provider backed by the LangSmith API."""

from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime, timedelta, timezone
from itertools import batched
from typing import Any, cast

from langsmith import AsyncClient
from nemo_platform_plugin.trace_provider import TraceQuery, TraceRef, TraceRow
from pydantic import BaseModel

_MAX_QUERY_WINDOW = timedelta(days=400)

_SUMMARY_SELECTS = [
    "ID",
    "TRACE_ID",
    "NAME",
    "RUN_TYPE",
    "STATUS",
    "START_TIME",
    "END_TIME",
    "ERROR_PREVIEW",
    "INPUTS_PREVIEW",
    "OUTPUTS_PREVIEW",
    "THREAD_ID",
    "TOTAL_TOKENS",
    "TOTAL_COST",
    "FEEDBACK_STATS",
    "TAGS",
]

_DETAIL_SELECTS = [
    "ID",
    "TRACE_ID",
    "PROJECT_ID",
    "NAME",
    "RUN_TYPE",
    "STATUS",
    "START_TIME",
    "END_TIME",
    "ERROR",
    "EXTRA",
    "METADATA",
    "EVENTS",
    "INPUTS",
    "OUTPUTS",
    "PARENT_RUN_IDS",
    "THREAD_ID",
    "DOTTED_ORDER",
    "IS_ROOT",
    "REFERENCE_EXAMPLE_ID",
    "TOTAL_TOKENS",
    "PROMPT_TOKENS",
    "COMPLETION_TOKENS",
    "TOTAL_COST",
    "PROMPT_COST",
    "COMPLETION_COST",
    "PROMPT_TOKEN_DETAILS",
    "COMPLETION_TOKEN_DETAILS",
    "PROMPT_COST_DETAILS",
    "COMPLETION_COST_DETAILS",
    "TAGS",
    "FEEDBACK_STATS",
]


def _dump(model: BaseModel) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json", exclude_none=True))


class LangSmithTraceProvider:
    """Discover and hydrate traces from one LangSmith tracing project."""

    name = "langsmith"

    def __init__(self, client: AsyncClient, *, project_id: str) -> None:
        if not project_id:
            raise ValueError("LangSmith project id must not be empty")
        self.client = client
        self.project_id = project_id
        self._project_started_at: datetime | None = None

    async def _project_start_time(self) -> datetime:
        if self._project_started_at is None:
            project = await self.client.read_project(project_id=self.project_id)
            self._project_started_at = project.start_time
        return self._project_started_at

    async def _query_windows(self, query: TraceQuery) -> list[tuple[datetime, datetime]]:
        lower_bound = query.started_after or await self._project_start_time()
        upper_bound = query.started_before or datetime.now(timezone.utc)
        return _split_time_range(lower_bound, upper_bound)

    async def filter_traces(self, query: TraceQuery) -> AsyncIterator[TraceRef]:
        yielded = 0
        seen: set[str] = set()
        trace_ids: tuple[str | None, ...] = query.ids or (None,)
        for trace_id in trace_ids:
            for min_start_time, max_start_time in await self._query_windows(query):
                kwargs: dict[str, Any] = {
                    "project_ids": [self.project_id],
                    "is_root": True,
                    "min_start_time": min_start_time,
                    "max_start_time": max_start_time,
                    "page_size": min(query.limit - yielded, 1000),
                    "selects": _SUMMARY_SELECTS,
                }
                if query.has_error is not None:
                    kwargs["has_error"] = query.has_error
                if trace_id is not None:
                    kwargs["trace_id"] = trace_id

                async for run in self.client.runs.query(**kwargs):
                    if query.has_error is True and run.status != "error":
                        continue
                    if query.has_error is False and run.status != "success":
                        continue
                    ref_id = run.trace_id or run.id
                    if not ref_id:
                        raise ValueError("LangSmith root run did not include an id or trace_id")
                    ref_id = str(ref_id)
                    if ref_id in seen:
                        continue
                    seen.add(ref_id)
                    yield TraceRef(id=ref_id, summary=_dump(run))
                    yielded += 1
                    if yielded >= query.limit:
                        return

    async def read_traces(self, traces: AsyncIterable[TraceRef]) -> AsyncIterator[TraceRow]:
        async for ref in traces:
            windows = _split_time_range(
                await self._project_start_time(),
                datetime.now(timezone.utc),
            )
            runs_by_id: dict[str, dict[str, object]] = {}
            for min_start_time, max_start_time in windows:
                async for run in self.client.runs.query(
                    project_ids=[self.project_id],
                    trace_id=ref.id,
                    min_start_time=min_start_time,
                    max_start_time=max_start_time,
                    page_size=1000,
                    selects=cast(Any, _DETAIL_SELECTS),
                ):
                    if not run.id:
                        raise ValueError(f"LangSmith trace {ref.id!r} contained a run without an id")
                    runs_by_id[str(run.id)] = _dump(run)
            runs = list(runs_by_id.values())
            if not runs:
                raise LookupError(f"LangSmith trace {ref.id!r} was not found in project {self.project_id!r}")

            feedback: list[dict[str, object]] = []
            for batch in batched(runs_by_id, 100):
                async for item in self.client.list_feedback(run_ids=list(batch)):
                    feedback.append(_dump(item))

            yield TraceRow(
                id=ref.id,
                data={
                    "source": self.name,
                    "project_id": self.project_id,
                    "runs": runs,
                    "feedback": feedback,
                },
            )


def _split_time_range(lower_bound: datetime, upper_bound: datetime) -> list[tuple[datetime, datetime]]:
    if lower_bound > upper_bound:
        return []
    windows: list[tuple[datetime, datetime]] = []
    cursor = upper_bound
    while cursor > lower_bound:
        window_start = max(lower_bound, cursor - _MAX_QUERY_WINDOW)
        windows.append((window_start, cursor))
        cursor = window_start
    if not windows:
        windows.append((lower_bound, upper_bound))
    return windows
