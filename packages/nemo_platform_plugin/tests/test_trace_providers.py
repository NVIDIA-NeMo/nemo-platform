# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import builtins
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from langsmith import AsyncClient
from mlflow import MlflowClient
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.intake_trace_provider import IntakeTraceProvider
from nemo_platform_plugin.langsmith_trace_provider import LangSmithTraceProvider
from nemo_platform_plugin.mlflow_trace_provider import MLflowTraceProvider
from nemo_platform_plugin.trace_provider import TraceProvider, TraceQuery, TraceRef
from pydantic import BaseModel, ConfigDict

_STARTED_AT = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


class _EvaluationContext(BaseModel):
    evaluation_id: str | None = None


class _Record(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    trace_id: str | None = None
    session_id: str | None = None
    started_at: datetime | None = None
    start_time: datetime | None = None
    status: str | None = None
    agent_name: str | None = None
    evaluation_context: _EvaluationContext | None = None


async def _iterate(items: list[_Record]) -> AsyncIterator[_Record]:
    for item in items:
        yield item


async def _refs(*ids: str) -> AsyncIterator[TraceRef]:
    for trace_id in ids:
        yield TraceRef(trace_id)


class _IntakeTraces:
    def __init__(self, trace: _Record) -> None:
        self.trace = trace
        self.list_calls: list[dict[str, object]] = []
        self.retrieve_calls: list[tuple[str, dict[str, object]]] = []

    def list(self, **kwargs: object) -> AsyncIterator[_Record]:
        self.list_calls.append(kwargs)
        return _iterate([self.trace])

    async def retrieve(self, trace_id: str, **kwargs: object) -> _Record:
        self.retrieve_calls.append((trace_id, kwargs))
        return self.trace


class _IntakeSpans:
    def __init__(self, spans: builtins.list[_Record], results: builtins.list[_Record]) -> None:
        self.spans = spans
        self.list_calls: list[dict[str, object]] = []
        self.evaluator_results = SimpleNamespace(list=self._list_results)
        self._results = results

    def list(self, **kwargs: object) -> AsyncIterator[_Record]:
        self.list_calls.append(kwargs)
        return _iterate(self.spans)

    async def _list_results(self, span_id: str, **kwargs: object) -> builtins.list[_Record]:
        del span_id, kwargs
        return self._results


class _IntakeAnnotations:
    def __init__(self, annotations: builtins.list[_Record]) -> None:
        self.annotations = annotations
        self.list_calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> AsyncIterator[_Record]:
        self.list_calls.append(kwargs)
        return _iterate(self.annotations)


def _intake_client(
    trace: _Record | None = None,
) -> tuple[AsyncNeMoPlatform, _IntakeTraces, _IntakeSpans, _IntakeAnnotations]:
    trace = trace or _Record(
        id="trace-1",
        trace_id="trace-1",
        session_id="session-1",
        started_at=_STARTED_AT,
        status="error",
    )
    traces = _IntakeTraces(trace)
    spans = _IntakeSpans([_Record(id="span-1", trace_id="trace-1")], [_Record(id="score-1")])
    annotations = _IntakeAnnotations([_Record(id="annotation-1")])
    client = SimpleNamespace(intake=SimpleNamespace(traces=traces, spans=spans, annotations=annotations))
    return cast(AsyncNeMoPlatform, client), traces, spans, annotations


def test_trace_query_rejects_invalid_bounds_and_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        TraceQuery(limit=0)
    with pytest.raises(ValueError, match="ids"):
        TraceQuery(ids=("",))
    with pytest.raises(ValueError, match="timezone"):
        TraceQuery(started_after=datetime(2026, 8, 20, 12))
    with pytest.raises(ValueError, match="started_after"):
        TraceQuery(started_after=_STARTED_AT, started_before=datetime(2026, 8, 19, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_intake_provider_filters_portable_query() -> None:
    client, traces, _, _ = _intake_client()
    provider = IntakeTraceProvider(
        client,
        workspace="default",
        agent_name="research-agent",
        evaluation_id="eval-1",
    )
    contract: TraceProvider = provider

    refs = [
        ref async for ref in contract.filter_traces(TraceQuery(started_after=_STARTED_AT, has_error=True, limit=10))
    ]

    assert refs == [TraceRef(id="trace-1", summary=refs[0].summary)]
    assert traces.list_calls == [
        {
            "workspace": "default",
            "filter": {
                "agent_name": "research-agent",
                "evaluation_id": "eval-1",
                "status": "error",
                "started_at": {"gte": _STARTED_AT},
            },
            "mode": "preview",
            "page_size": 10,
            "sort": "-started_at",
        }
    ]


@pytest.mark.parametrize(
    ("trace_agent", "trace_evaluation"),
    [
        ("other-agent", "eval-1"),
        ("research-agent", "other-eval"),
    ],
)
@pytest.mark.asyncio
async def test_intake_provider_filters_ids_within_scope(trace_agent: str, trace_evaluation: str) -> None:
    client, traces, _, _ = _intake_client(
        _Record(
            id="trace-1",
            trace_id="trace-1",
            session_id="session-1",
            started_at=_STARTED_AT,
            status="error",
            agent_name=trace_agent,
            evaluation_context=_EvaluationContext(evaluation_id=trace_evaluation),
        )
    )
    provider = IntakeTraceProvider(
        client,
        workspace="default",
        agent_name="research-agent",
        evaluation_id="eval-1",
    )

    refs = [ref async for ref in provider.filter_traces(TraceQuery(ids=("trace-1",), limit=5))]

    assert refs == []
    assert traces.retrieve_calls == [("trace-1", {"workspace": "default", "mode": "preview"})]


@pytest.mark.asyncio
async def test_intake_provider_filters_ids_to_completed_successes() -> None:
    client, _, _, _ = _intake_client(
        _Record(
            id="trace-1",
            trace_id="trace-1",
            session_id="session-1",
            started_at=_STARTED_AT,
            status="unknown",
        )
    )
    provider = IntakeTraceProvider(client, workspace="default")

    refs = [ref async for ref in provider.filter_traces(TraceQuery(ids=("trace-1",), has_error=False, limit=5))]

    assert refs == []


@pytest.mark.asyncio
async def test_intake_provider_hydrates_trace_signals() -> None:
    client, traces, spans, annotations = _intake_client()
    provider = IntakeTraceProvider(client, workspace="default")

    rows = [row async for row in provider.read_traces(_refs("trace-1"))]

    assert len(rows) == 1
    assert rows[0].id == "trace-1"
    assert rows[0].data["source"] == "intake"
    assert cast(list[dict[str, object]], rows[0].data["spans"])[0]["id"] == "span-1"
    assert cast(list[dict[str, object]], rows[0].data["annotations"])[0]["id"] == "annotation-1"
    assert cast(list[dict[str, object]], rows[0].data["evaluator_results"])[0]["span_id"] == "span-1"
    assert traces.retrieve_calls == [("trace-1", {"workspace": "default", "mode": "detailed"})]
    assert spans.list_calls[0]["filter"] == {"trace_id": "trace-1"}
    assert annotations.list_calls[0]["filter"] == {"session_id": "session-1"}


@pytest.mark.asyncio
async def test_intake_provider_rejects_hydration_outside_scope() -> None:
    client, _, spans, _ = _intake_client(
        _Record(
            id="trace-1",
            trace_id="trace-1",
            session_id="session-1",
            started_at=_STARTED_AT,
            status="error",
            agent_name="other-agent",
        )
    )
    provider = IntakeTraceProvider(client, workspace="default", agent_name="research-agent")

    with pytest.raises(LookupError, match="configured provider scope"):
        _ = [row async for row in provider.read_traces(_refs("trace-1"))]

    assert spans.list_calls == []


class _LangSmithRuns:
    def __init__(self, responses: list[list[_Record]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def query(self, **kwargs: object) -> AsyncIterator[_Record]:
        self.calls.append(kwargs)
        return _iterate(self.responses.pop(0))


class _LangSmithClient:
    def __init__(self, runs: _LangSmithRuns, feedback: list[_Record] | None = None) -> None:
        self.runs = runs
        self.feedback = feedback or []
        self.feedback_calls: list[list[str]] = []

    async def read_project(self, *, project_id: str) -> SimpleNamespace:
        assert project_id == "project-1"
        return SimpleNamespace(start_time=_STARTED_AT - timedelta(days=1))

    async def list_feedback(self, *, run_ids: list[str]) -> AsyncIterator[_Record]:
        self.feedback_calls.append(run_ids)
        for item in self.feedback:
            yield item


@pytest.mark.asyncio
async def test_langsmith_provider_filters_root_runs() -> None:
    runs = _LangSmithRuns([[_Record(id="run-1", trace_id="trace-1", start_time=_STARTED_AT, status="error")]])
    client = _LangSmithClient(runs)
    provider = LangSmithTraceProvider(cast(AsyncClient, client), project_id="project-1")
    contract: TraceProvider = provider

    refs = [ref async for ref in contract.filter_traces(TraceQuery(has_error=True, limit=5))]

    assert refs[0].id == "trace-1"
    assert runs.calls[0]["project_ids"] == ["project-1"]
    assert runs.calls[0]["is_root"] is True
    assert runs.calls[0]["has_error"] is True
    assert runs.calls[0]["page_size"] == 5


@pytest.mark.asyncio
async def test_langsmith_provider_filters_to_completed_successes() -> None:
    runs = _LangSmithRuns(
        [
            [
                _Record(id="run-pending", trace_id="trace-pending", start_time=_STARTED_AT, status="pending"),
                _Record(id="run-success", trace_id="trace-success", start_time=_STARTED_AT, status="success"),
            ]
        ]
    )
    client = _LangSmithClient(runs)
    provider = LangSmithTraceProvider(cast(AsyncClient, client), project_id="project-1")

    refs = [ref async for ref in provider.filter_traces(TraceQuery(has_error=False, limit=5))]

    assert [ref.id for ref in refs] == ["trace-success"]


@pytest.mark.asyncio
async def test_langsmith_provider_splits_wide_time_ranges() -> None:
    runs = _LangSmithRuns([[], [], []])
    client = _LangSmithClient(runs)
    provider = LangSmithTraceProvider(cast(AsyncClient, client), project_id="project-1")

    refs = [
        ref
        async for ref in provider.filter_traces(
            TraceQuery(
                started_after=_STARTED_AT - timedelta(days=801),
                started_before=_STARTED_AT,
                limit=5,
            )
        )
    ]

    assert refs == []
    assert len(runs.calls) == 3
    assert all(
        cast(datetime, call["max_start_time"]) - cast(datetime, call["min_start_time"]) <= timedelta(days=400)
        for call in runs.calls
    )


@pytest.mark.asyncio
async def test_langsmith_provider_hydrates_run_tree_and_feedback() -> None:
    runs = _LangSmithRuns([[_Record(id="run-1", trace_id="trace-1"), _Record(id="run-2", trace_id="trace-1")]])
    client = _LangSmithClient(runs, feedback=[_Record(id="feedback-1")])
    provider = LangSmithTraceProvider(cast(AsyncClient, client), project_id="project-1")

    rows = [row async for row in provider.read_traces(_refs("trace-1"))]

    assert rows[0].data["source"] == "langsmith"
    assert [item["id"] for item in cast(list[dict[str, object]], rows[0].data["runs"])] == [
        "run-1",
        "run-2",
    ]
    assert cast(list[dict[str, object]], rows[0].data["feedback"])[0]["id"] == "feedback-1"
    assert runs.calls[0]["trace_id"] == "trace-1"
    assert client.feedback_calls == [["run-1", "run-2"]]


class _MLflowInfo:
    def __init__(
        self,
        *,
        trace_id: str,
        experiment_id: str = "experiment-1",
        timestamp_ms: int = int(_STARTED_AT.timestamp() * 1000),
        state: str = "ERROR",
    ) -> None:
        self.trace_id = trace_id
        self.experiment_id = experiment_id
        self.timestamp_ms = timestamp_ms
        self.state = SimpleNamespace(value=state)

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "experiment_id": self.experiment_id,
            "request_time": self.timestamp_ms,
            "state": self.state.value,
        }


class _MLflowTrace:
    def __init__(
        self,
        trace_id: str,
        *,
        experiment_id: str = "experiment-1",
        timestamp_ms: int = int(_STARTED_AT.timestamp() * 1000),
        state: str = "ERROR",
    ) -> None:
        self.info = _MLflowInfo(
            trace_id=trace_id,
            experiment_id=experiment_id,
            timestamp_ms=timestamp_ms,
            state=state,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "info": {**self.info.to_dict(), "assessments": [{"assessment_name": "correctness"}]},
            "data": {"spans": [{"name": "check_inventory"}]},
        }


class _MLflowPage(list[_MLflowTrace]):
    def __init__(self, traces: list[_MLflowTrace], *, token: str | None = None) -> None:
        super().__init__(traces)
        self.token = token


class _MLflowClient:
    def __init__(self, traces: list[_MLflowTrace], pages: list[_MLflowPage] | None = None) -> None:
        self.traces = {trace.info.trace_id: trace for trace in traces}
        self.pages = pages or [_MLflowPage(traces)]
        self.search_calls: list[dict[str, object]] = []
        self.get_calls: list[tuple[str, bool]] = []

    def search_traces(self, **kwargs: object) -> _MLflowPage:
        self.search_calls.append(kwargs)
        return self.pages.pop(0)

    def get_trace(self, trace_id: str, display: bool = True) -> _MLflowTrace:
        self.get_calls.append((trace_id, display))
        return self.traces[trace_id]


@pytest.mark.asyncio
async def test_mlflow_provider_filters_portable_query() -> None:
    trace = _MLflowTrace("tr-trace-1")
    client = _MLflowClient([trace])
    provider = MLflowTraceProvider(cast(MlflowClient, client), experiment_id="experiment-1")
    contract: TraceProvider = provider

    refs = [
        ref
        async for ref in contract.filter_traces(
            TraceQuery(
                started_after=_STARTED_AT,
                started_before=_STARTED_AT + timedelta(hours=1),
                has_error=True,
                limit=5,
            )
        )
    ]

    assert refs[0].id == "tr-trace-1"
    assert client.search_calls == [
        {
            "locations": ["experiment-1"],
            "filter_string": (
                "trace.status = 'ERROR' "
                f"AND trace.timestamp_ms >= {int(_STARTED_AT.timestamp() * 1000)} "
                f"AND trace.timestamp_ms <= {int((_STARTED_AT + timedelta(hours=1)).timestamp() * 1000)}"
            ),
            "max_results": 5,
            "order_by": ["timestamp_ms DESC"],
            "page_token": None,
            "include_spans": False,
        }
    ]


@pytest.mark.asyncio
async def test_mlflow_provider_filters_ids_within_experiment() -> None:
    matching = _MLflowTrace("tr-matching")
    other_experiment = _MLflowTrace("tr-other", experiment_id="experiment-2")
    client = _MLflowClient([matching, other_experiment])
    provider = MLflowTraceProvider(cast(MlflowClient, client), experiment_id="experiment-1")

    refs = [
        ref
        async for ref in provider.filter_traces(TraceQuery(ids=("tr-matching", "tr-other"), has_error=True, limit=5))
    ]

    assert [ref.id for ref in refs] == ["tr-matching"]
    assert client.get_calls == [("tr-matching", False), ("tr-other", False)]


@pytest.mark.asyncio
async def test_mlflow_provider_filters_ids_to_completed_successes() -> None:
    success = _MLflowTrace("tr-success", state="OK")
    in_progress = _MLflowTrace("tr-in-progress", state="IN_PROGRESS")
    error = _MLflowTrace("tr-error", state="ERROR")
    client = _MLflowClient([success, in_progress, error])
    provider = MLflowTraceProvider(cast(MlflowClient, client), experiment_id="experiment-1")

    refs = [
        ref
        async for ref in provider.filter_traces(
            TraceQuery(ids=("tr-success", "tr-in-progress", "tr-error"), has_error=False, limit=5)
        )
    ]

    assert [ref.id for ref in refs] == ["tr-success"]


@pytest.mark.asyncio
async def test_mlflow_provider_paginates_search_results() -> None:
    first = _MLflowTrace("tr-first")
    second = _MLflowTrace("tr-second")
    client = _MLflowClient(
        [first, second],
        pages=[
            _MLflowPage([first], token="next-page"),
            _MLflowPage([second]),
        ],
    )
    provider = MLflowTraceProvider(cast(MlflowClient, client), experiment_id="experiment-1")

    refs = [ref async for ref in provider.filter_traces(TraceQuery(limit=5))]

    assert [ref.id for ref in refs] == ["tr-first", "tr-second"]
    assert [call["page_token"] for call in client.search_calls] == [None, "next-page"]
    assert [call["max_results"] for call in client.search_calls] == [5, 4]


@pytest.mark.asyncio
async def test_mlflow_provider_hydrates_native_trace() -> None:
    trace = _MLflowTrace("tr-trace-1")
    client = _MLflowClient([trace])
    provider = MLflowTraceProvider(cast(MlflowClient, client), experiment_id="experiment-1")

    rows = [row async for row in provider.read_traces(_refs("tr-trace-1"))]

    assert rows[0].data["source"] == "mlflow"
    assert rows[0].data["experiment_id"] == "experiment-1"
    native = cast(dict[str, object], rows[0].data["trace"])
    data = cast(dict[str, object], native["data"])
    assert cast(list[dict[str, object]], data["spans"])[0]["name"] == "check_inventory"
    info = cast(dict[str, object], native["info"])
    assert cast(list[dict[str, object]], info["assessments"])[0]["assessment_name"] == "correctness"
    assert client.get_calls == [("tr-trace-1", False)]
