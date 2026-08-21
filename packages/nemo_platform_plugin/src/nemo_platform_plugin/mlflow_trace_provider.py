# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace provider backed by the MLflow Tracking API."""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime
from functools import partial
from typing import cast

from mlflow import MlflowClient
from mlflow.entities import Trace
from nemo_platform_plugin.trace_provider import TraceQuery, TraceRef, TraceRow


def _milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _matches(trace: Trace, query: TraceQuery) -> bool:
    timestamp_ms = trace.info.timestamp_ms
    if query.started_after is not None and timestamp_ms < _milliseconds(query.started_after):
        return False
    if query.started_before is not None and timestamp_ms > _milliseconds(query.started_before):
        return False
    if query.has_error is True and trace.info.state.value != "ERROR":
        return False
    if query.has_error is False and trace.info.state.value != "OK":
        return False
    return True


def _summary(trace: Trace) -> dict[str, object]:
    return cast(dict[str, object], trace.info.to_dict())


class MLflowTraceProvider:
    """Discover and hydrate traces from one MLflow experiment."""

    name = "mlflow"

    def __init__(self, client: MlflowClient, *, experiment_id: str) -> None:
        if not experiment_id:
            raise ValueError("MLflow experiment id must not be empty")
        self.client = client
        self.experiment_id = experiment_id

    async def filter_traces(self, query: TraceQuery) -> AsyncIterator[TraceRef]:
        if query.ids:
            yielded = 0
            for trace_id in query.ids:
                trace = await asyncio.to_thread(self.client.get_trace, trace_id, False)
                if trace.info.experiment_id != self.experiment_id or not _matches(trace, query):
                    continue
                yield TraceRef(id=trace.info.trace_id, summary=_summary(trace))
                yielded += 1
                if yielded >= query.limit:
                    return
            return

        filter_string = _filter_string(query)
        page_token: str | None = None
        yielded = 0
        while yielded < query.limit:
            page = await asyncio.to_thread(
                partial(
                    self.client.search_traces,
                    locations=[self.experiment_id],
                    filter_string=filter_string or None,
                    max_results=min(query.limit - yielded, 1000),
                    order_by=["timestamp_ms DESC"],
                    page_token=page_token,
                    include_spans=False,
                )
            )
            for trace in page:
                yield TraceRef(id=trace.info.trace_id, summary=_summary(trace))
                yielded += 1
                if yielded >= query.limit:
                    return
            page_token = page.token
            if not page_token:
                return

    async def read_traces(self, traces: AsyncIterable[TraceRef]) -> AsyncIterator[TraceRow]:
        async for ref in traces:
            trace = await asyncio.to_thread(self.client.get_trace, ref.id, False)
            if trace.info.experiment_id != self.experiment_id:
                raise LookupError(f"MLflow trace {ref.id!r} was not found in experiment {self.experiment_id!r}")
            yield TraceRow(
                id=ref.id,
                data={
                    "source": self.name,
                    "experiment_id": self.experiment_id,
                    "trace": cast(dict[str, object], trace.to_dict()),
                },
            )


def _filter_string(query: TraceQuery) -> str:
    filters: list[str] = []
    if query.has_error is not None:
        filters.append(f"trace.status = '{'ERROR' if query.has_error else 'OK'}'")
    if query.started_after is not None:
        filters.append(f"trace.timestamp_ms >= {_milliseconds(query.started_after)}")
    if query.started_before is not None:
        filters.append(f"trace.timestamp_ms <= {_milliseconds(query.started_before)}")
    return " AND ".join(filters)
