# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Eval Author's Intake trace tools.

Only the logic this module owns: what the raw queries send and return, how the
composite dedupes and merges, ref normalization, and the error messages. Reading and
diagnosing a trace belong to Experimentalist, so those seams are faked.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from nemo_eval_author_plugin import traces
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor
from nemo_platform import APIConnectionError, APIStatusError

_BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _at(minute: int) -> str:
    return (_BASE + timedelta(minutes=minute)).isoformat()


class _Row:
    """A stand-in for an SDK model. Only ``model_dump`` is used."""

    def __init__(self, **fields: Any) -> None:
        self._fields = fields

    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {name: value for name, value in self._fields.items() if value is not None}


def _span(trace_id: str | None, *, minute: int, **fields: Any) -> _Row:
    return _Row(trace_id=trace_id, started_at=_at(minute), span_id=f"s-{minute}", **fields)


def _summary(trace_id: str, *, minute: int, **fields: Any) -> _Row:
    return _Row(
        id=trace_id,
        started_at=_at(minute),
        status=fields.pop("status", "success"),
        span_count=fields.pop("span_count", 1),
        error_count=fields.pop("error_count", 0),
        **fields,
    )


def _pages(items: list[Any], error: Exception | None) -> Any:
    async def stream() -> Any:
        if error is not None:
            raise error
        for item in items:
            yield item

    return stream()


class _FakeClient:
    """Stands in for the three Intake reads these tools make."""

    def __init__(
        self,
        spans: list[_Row],
        summaries: list[_Row],
        groups: list[_Row],
        error: Exception | None,
    ) -> None:
        self._spans = spans
        self._summaries = summaries
        self._groups = groups
        self._error = error
        self.span_calls: list[dict[str, Any]] = []
        self.trace_calls: list[dict[str, Any]] = []
        self.group_calls: list[dict[str, Any]] = []
        self.intake = SimpleNamespace(
            spans=SimpleNamespace(
                list=self._list_spans,
                groups=SimpleNamespace(list=self._list_groups),
            ),
            traces=SimpleNamespace(list=self._list_traces),
        )

    def _list_spans(self, **kwargs: Any) -> Any:
        self.span_calls.append(kwargs)
        return _pages(self._spans, self._error)

    def _list_groups(self, **kwargs: Any) -> Any:
        self.group_calls.append(kwargs)
        return _pages(self._groups, self._error)

    def _list_traces(self, **kwargs: Any) -> Any:
        self.trace_calls.append(kwargs)
        rows = self._summaries
        wanted = kwargs.get("filter", {}).get("id", {}).get("$in")
        if wanted is not None:
            rows = [row for row in rows if row.model_dump()["id"] in set(wanted)]
        return _pages(rows, self._error)


def _client(
    spans: list[_Row] | None = None,
    summaries: list[_Row] | None = None,
    groups: list[_Row] | None = None,
    error: Exception | None = None,
) -> Any:
    """A fake platform client, typed ``Any`` so call sites need no cast."""
    return _FakeClient(spans or [], summaries or [], groups or [], error)


def _status_error(code: int) -> APIStatusError:
    request = httpx.Request("GET", "https://example.invalid/spans")
    return APIStatusError("boom", response=httpx.Response(code, request=request), body=None)


# --- raw queries -------------------------------------------------------------------


async def test_query_spans_sends_the_filter_and_returns_plain_rows() -> None:
    client = _client(spans=[_span("t-1", minute=5, tool_name="search")])

    result = await traces.query_spans(
        client,
        workspace="ws",
        filter={"agent_name": "aut", "tool_name": "search", "status": "error"},
        mode="detailed",
        limit=10,
    )

    call = client.span_calls[0]
    assert call["filter"] == {"agent_name": "aut", "tool_name": "search", "status": "error"}
    assert call["mode"] == "detailed"
    assert call["sort"] == "-started_at"
    assert result["count"] == 1
    assert result["truncated"] is False
    assert result["spans"][0]["tool_name"] == "search"


async def test_query_spans_omits_an_absent_filter() -> None:
    # The SDK uses an omit sentinel, so a None filter must not be sent as null.
    client = _client()

    await traces.query_spans(client, workspace="ws")

    assert "filter" not in client.span_calls[0]


async def test_query_spans_truncates_at_the_limit() -> None:
    client = _client(spans=[_span(f"t-{index}", minute=index) for index in range(10)])

    result = await traces.query_spans(client, workspace="ws", limit=4)

    assert result["count"] == 4
    assert result["truncated"] is True


async def test_query_spans_groups_server_side() -> None:
    client = _client(groups=[_Row(group={"trace_id": "t-1"}, span_count=12)])

    result = await traces.query_spans(client, workspace="ws", filter={"tool_name": "search"}, group_by="trace_id")

    assert client.group_calls[0]["by"] == "trace_id"
    assert client.group_calls[0]["filter"] == {"tool_name": "search"}
    assert client.span_calls == []
    assert result["grouped_by"] == "trace_id"
    assert result["groups"][0]["span_count"] == 12


async def test_query_traces_defaults_to_preview_for_the_rollups() -> None:
    client = _client(summaries=[_summary("t-1", minute=5, span_count=40, error_count=3)])

    result = await traces.query_traces(client, workspace="ws", filter={"id": {"$in": ["t-1"]}})

    assert client.trace_calls[0]["mode"] == "preview"
    assert client.trace_calls[0]["sort"] == "-started_at"
    assert result["traces"][0]["span_count"] == 40
    assert result["traces"][0]["error_count"] == 3


# --- the composite -----------------------------------------------------------------


async def test_find_agent_traces_dedupes_and_orders_newest_first() -> None:
    client = _client(
        spans=[
            _span("t-new", minute=50),
            _span("t-old", minute=20),
            _span("t-new", minute=40),
            _span(None, minute=15),
        ],
        summaries=[_summary("t-new", minute=40), _summary("t-old", minute=10)],
    )

    result = await traces.find_agent_traces(client, agent="aut", workspace="ws")

    assert [trace["trace_ref"] for trace in result["traces"]] == ["intake://t-new", "intake://t-old"]
    assert result["traces"][0]["trace_id"] == "t-new"
    assert result["count"] == 2
    assert result["truncated"] is False


async def test_find_agent_traces_uses_the_server_summary() -> None:
    # The scan sees two spans and no error. The server knows the trace holds 40 spans
    # and three errors. Counting the window alone would report a healthy trace.
    client = _client(
        spans=[_span("t-1", minute=50), _span("t-1", minute=49)],
        summaries=[_summary("t-1", minute=10, status="error", span_count=40, error_count=3, name="run")],
    )

    result = await traces.find_agent_traces(client, agent="aut", workspace="ws")

    trace = result["traces"][0]
    assert trace["status"] == "error"
    assert trace["span_count"] == 40
    assert trace["error_count"] == 3
    assert trace["name"] == "run"
    assert trace["started_at"] == _at(10)
    assert client.trace_calls[0]["filter"] == {"id": {"$in": ["t-1"]}}


async def test_find_agent_traces_keeps_a_trace_with_no_summary() -> None:
    # A trace whose root span was never ingested has no traces.list row. It must still
    # be returned, and its unknown fields must not read as zero.
    client = _client(spans=[_span("t-1", minute=30)], summaries=[])

    result = await traces.find_agent_traces(client, agent="aut", workspace="ws")

    trace = result["traces"][0]
    assert trace["trace_ref"] == "intake://t-1"
    assert trace["status"] == "unknown"
    assert trace["span_count"] is None
    assert trace["error_count"] is None


async def test_find_agent_traces_chunks_trace_ids() -> None:
    client = _client(
        spans=[_span(f"t-{index}", minute=index) for index in range(120)],
        summaries=[_summary(f"t-{index}", minute=index) for index in range(120)],
    )

    result = await traces.find_agent_traces(client, agent="aut", workspace="ws", limit=120, span_budget=200)

    assert result["count"] == 120
    assert [len(call["filter"]["id"]["$in"]) for call in client.trace_calls] == [50, 50, 20]


async def test_find_agent_traces_truncates_on_the_span_budget() -> None:
    client = _client(spans=[_span(f"t-{index}", minute=index) for index in range(10)])

    result = await traces.find_agent_traces(client, agent="aut", workspace="ws", span_budget=4)

    assert result["count"] == 4
    assert result["truncated"] is True


async def test_find_agent_traces_truncates_on_the_trace_limit() -> None:
    client = _client(spans=[_span(f"t-{index}", minute=index) for index in range(10)])

    result = await traces.find_agent_traces(client, agent="aut", workspace="ws", limit=3)

    assert result["count"] == 3
    assert result["truncated"] is True


async def test_find_agent_traces_sends_since() -> None:
    client = _client()
    since = _BASE + timedelta(minutes=30)

    await traces.find_agent_traces(client, agent="aut", workspace="ws", since=since)

    assert client.span_calls[0]["filter"] == {"agent_name": "aut", "started_at": {"gte": since.isoformat()}}


async def test_find_agent_traces_empty_result_is_not_an_error() -> None:
    client = _client()

    result = await traces.find_agent_traces(client, agent="typo-agent", workspace="ws")

    assert result["count"] == 0
    assert "typo-agent" in result["note"]
    assert "ws" in result["note"]
    # Nothing to summarize, so the second call must not be made.
    assert client.trace_calls == []


# --- errors ------------------------------------------------------------------------


async def test_auth_failure_says_how_to_recover() -> None:
    client = _client(error=_status_error(401))

    with pytest.raises(traces.TraceQueryError, match="nemo auth login"):
        await traces.find_agent_traces(client, agent="aut", workspace="ws")


async def test_bad_filter_points_at_the_vocabulary() -> None:
    client = _client(error=_status_error(400))

    with pytest.raises(traces.TraceQueryError, match="filter fields and operators"):
        await traces.query_spans(client, workspace="ws", filter={"nonsense": 1})


async def test_internal_error_names_the_filters_intake_cannot_serve() -> None:
    # Intake publishes five span filters that raise instead of returning 400, so a bare
    # 500 is the only signal the agent gets. The message must name them.
    client = _client(error=_status_error(500))

    with pytest.raises(traces.TraceQueryError, match="prompt_name"):
        await traces.query_spans(client, workspace="ws", filter={"dataset_name": "x"})


async def test_unreachable_platform_names_the_base_url() -> None:
    request = httpx.Request("GET", "https://example.invalid/spans")
    client = _client(error=APIConnectionError(request=request))

    with pytest.raises(traces.TraceQueryError, match="NMP_BASE_URL"):
        await traces.query_traces(client, workspace="ws")


# --- reading and analysis ----------------------------------------------------------


@pytest.mark.parametrize("ref", ["t-1", "intake://t-1", "intake://traces/t-1"])
async def test_all_three_ref_spellings_reach_the_explorer(monkeypatch: pytest.MonkeyPatch, ref: str) -> None:
    seen: list[str] = []

    async def _from_ref(resource_ref: Any, client: Any, workspace: str) -> str:
        seen.append(resource_ref.uri)
        return "explorer"

    monkeypatch.setattr(traces.TraceExplorer, "from_ref", _from_ref)

    assert await traces.read_trace(_client(), ref, workspace="ws") == "explorer"  # type: ignore[comparison-overlap]
    # from_ref strips both prefixes itself, so a bare id only needs the scheme added.
    assert seen == [ref if ref.startswith("intake://") else "intake://t-1"]


async def test_missing_trace_names_the_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _from_ref(resource_ref: Any, client: Any, workspace: str) -> str:
        raise ValueError("No spans found in Intake for trace: t-gone")

    monkeypatch.setattr(traces.TraceExplorer, "from_ref", _from_ref)

    with pytest.raises(traces.TraceQueryError, match="No spans found in Intake for trace: t-gone") as caught:
        await traces.read_trace(_client(), "t-gone", workspace="ws")
    assert "ws" in str(caught.value)


async def test_read_trace_404_names_the_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _from_ref(resource_ref: Any, client: Any, workspace: str) -> str:
        raise _status_error(404)

    monkeypatch.setattr(traces.TraceExplorer, "from_ref", _from_ref)

    with pytest.raises(traces.TraceQueryError, match="workspace 'ws' exists"):
        await traces.read_trace(_client(), "t-gone", workspace="ws")


async def test_synthesized_task_starts_no_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeAnalyzer:
        def __init__(self, *, experiment_dir: Path) -> None:
            captured["experiment_dir"] = experiment_dir

        async def run(self, **kwargs: Any) -> str:
            captured.update(kwargs)
            return "diagnostic"

    monkeypatch.setattr(traces, "TraceAnalyzer", _FakeAnalyzer)

    result = await traces.analyze_trace(
        _client(),
        "intake://traces/t-1",
        workspace="ws",
        experiment_dir=Path("/tmp/experiment"),
        agent_path=Path("/tmp/agent"),
    )

    assert result == "diagnostic"
    assert captured["insight"] is None
    assert captured["trial"].trace.uri == "intake://t-1"
    # A production trace has no evaluator task, so the synthetic one must start nothing.
    async with captured["task"].start_deps() as runtime:
        assert runtime is None


# --- agent surface -----------------------------------------------------------------


def _agent(client: Any, workspace: str | None) -> Any:
    """An EvalAuthor with only the trace-tool attributes set.

    ``object.__new__`` skips ``__init__``, which builds an LLM client the trace tools
    do not touch.
    """
    eval_author = object.__new__(EvalAuthor)
    eval_author.client = client
    eval_author.workspace = workspace
    return eval_author


async def test_agent_trace_tools_say_what_is_missing() -> None:
    eval_author = _agent(None, None)

    with pytest.raises(traces.TraceQueryError, match="EvalAuthor.client"):
        await eval_author.find_agent_traces("aut")


async def test_agent_trace_tools_delegate() -> None:
    client = _client(
        spans=[_span("t-1", minute=10)],
        summaries=[_summary("t-1", minute=10, span_count=7)],
    )
    eval_author = _agent(client, "ws")

    found = await eval_author.find_agent_traces("aut")
    queried = await eval_author.query_spans(filter={"trace_id": "t-1"}, limit=5)

    assert found["traces"][0]["span_count"] == 7
    assert client.span_calls[-1]["filter"] == {"trace_id": "t-1"}
    assert queried["count"] == 1
