# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace provider backed by NeMo Intake."""

from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime
from typing import Any, cast

from nemo_platform import AsyncNeMoPlatform, omit
from nemo_platform.types.intake.annotation_filter_param import AnnotationFilterParam
from nemo_platform.types.intake.trace import Trace
from nemo_platform.types.intake.trace_filter_param import TraceFilterParam
from nemo_platform_plugin.trace_provider import TraceQuery, TraceRef, TraceRow
from pydantic import BaseModel


def _dump(model: BaseModel) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json", exclude_none=True))


def _within_window(started_at: datetime, query: TraceQuery) -> bool:
    if query.started_after is not None and started_at < query.started_after:
        return False
    if query.started_before is not None and started_at > query.started_before:
        return False
    return True


class IntakeTraceProvider:
    """Discover and hydrate traces from one Intake workspace and agent scope."""

    name = "intake"

    def __init__(
        self,
        client: AsyncNeMoPlatform,
        *,
        workspace: str,
        agent_name: str | None = None,
        evaluation_id: str | None = None,
    ) -> None:
        self.client = client
        self.workspace = workspace
        self.agent_name = agent_name
        self.evaluation_id = evaluation_id

    async def filter_traces(self, query: TraceQuery) -> AsyncIterator[TraceRef]:
        if query.ids:
            yielded = 0
            for trace_id in query.ids:
                trace = await self.client.intake.traces.retrieve(trace_id, workspace=self.workspace, mode="preview")
                if not self._matches_scope(trace):
                    continue
                if not _within_window(trace.started_at, query):
                    continue
                if query.has_error is True and trace.status != "error":
                    continue
                if query.has_error is False and trace.status != "success":
                    continue
                yield TraceRef(id=trace.id, summary=_dump(trace))
                yielded += 1
                if yielded >= query.limit:
                    return
            return

        filter_obj = self._filter(query)
        paginator = self.client.intake.traces.list(
            workspace=self.workspace,
            filter=filter_obj or omit,
            mode="preview",
            page_size=min(query.limit, 1000),
            sort="-started_at",
        )
        yielded = 0
        async for trace in paginator:
            yield TraceRef(id=trace.id, summary=_dump(trace))
            yielded += 1
            if yielded >= query.limit:
                return

    async def read_traces(self, traces: AsyncIterable[TraceRef]) -> AsyncIterator[TraceRow]:
        async for ref in traces:
            trace = await self.client.intake.traces.retrieve(ref.id, workspace=self.workspace, mode="detailed")
            if not self._matches_scope(trace):
                raise LookupError(f"Intake trace {ref.id!r} was not found in the configured provider scope")
            spans = [
                _dump(span)
                async for span in self.client.intake.spans.list(
                    workspace=self.workspace,
                    filter=cast(Any, {"trace_id": ref.id}),
                    mode="detailed",
                    page_size=1000,
                    sort="started_at",
                )
            ]
            annotations = [
                _dump(annotation)
                async for annotation in self.client.intake.annotations.list(
                    workspace=self.workspace,
                    filter=cast(AnnotationFilterParam, {"session_id": trace.session_id}),
                    page_size=1000,
                    sort="created_at",
                )
            ]
            evaluator_results: list[dict[str, object]] = []
            for span in spans:
                span_id = str(span["id"])
                results = await self.client.intake.spans.evaluator_results.list(span_id, workspace=self.workspace)
                serialized = [_dump(result) for result in results]
                if serialized:
                    evaluator_results.append({"span_id": span_id, "results": serialized})

            yield TraceRow(
                id=ref.id,
                data={
                    "source": self.name,
                    "trace": _dump(trace),
                    "spans": spans,
                    "annotations": annotations,
                    "evaluator_results": evaluator_results,
                },
            )

    def _matches_scope(self, trace: Trace) -> bool:
        if self.agent_name is not None and trace.agent_name != self.agent_name:
            return False
        evaluation_id = trace.evaluation_context.evaluation_id if trace.evaluation_context is not None else None
        return self.evaluation_id is None or evaluation_id == self.evaluation_id

    def _filter(self, query: TraceQuery) -> TraceFilterParam:
        filter_obj: TraceFilterParam = {}
        if self.agent_name:
            filter_obj["agent_name"] = self.agent_name
        if self.evaluation_id:
            filter_obj["evaluation_id"] = self.evaluation_id
        if query.has_error is not None:
            filter_obj["status"] = "error" if query.has_error else "success"
        started_at: dict[str, datetime] = {}
        if query.started_after is not None:
            started_at["gte"] = query.started_after
        if query.started_before is not None:
            started_at["lte"] = query.started_before
        if started_at:
            filter_obj["started_at"] = cast(Any, started_at)
        return filter_obj
