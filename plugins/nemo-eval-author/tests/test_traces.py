# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Eval Author's Intake trace tools.

Only the logic this module owns: the span scan, the merge of the server summary over
it, the client-side facet counts, ref normalization, and the error messages. Reading
and diagnosing a trace belong to Experimentalist, so those seams are faked.
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


def _at(minute: int) -> datetime:
    return _BASE + timedelta(minutes=minute)


def _span(trace_id: str, *, minute: int, **fields: Any) -> SimpleNamespace:
    """One Intake span row, with only the fields the scan reads."""
    return SimpleNamespace(
        trace_id=trace_id,
        started_at=_at(minute),
        status=fields.pop("status", "success"),
        error_type=fields.pop("error_type", None),
        name=fields.pop("name", None),
        tool_name=fields.pop("tool_name", None),
        model=fields.pop("model", None),
        **fields,
    )


def _summary(trace_id: str, *, minute: int, **fields: Any) -> SimpleNamespace:
    """One ``traces.list`` row: the server-computed summary of a whole trace."""
    return SimpleNamespace(
        id=trace_id,
        started_at=_at(minute),
        status=fields.pop("status", "success"),
        span_count=fields.pop("span_count", 1),
        error_count=fields.pop("error_count", 0),
        duration_ms=fields.pop("duration_ms", None),
        name=fields.pop("name", None),
        **fields,
    )


def _pages(items: list[SimpleNamespace], error: Exception | None) -> Any:
    async def stream() -> Any:
        if error is not None:
            raise error
        for item in items:
            yield item

    return stream()


class _FakeClient:
    """Stands in for the two Intake reads that ``list_traces`` makes."""

    def __init__(
        self,
        spans: list[SimpleNamespace],
        summaries: list[SimpleNamespace],
        error: Exception | None,
    ) -> None:
        self._spans = spans
        self._summaries = summaries
        self._error = error
        self.span_calls: list[dict[str, Any]] = []
        self.trace_calls: list[dict[str, Any]] = []
        self.intake = SimpleNamespace(
            spans=SimpleNamespace(list=self._list_spans),
            traces=SimpleNamespace(list=self._list_traces),
        )

    def _list_spans(self, **kwargs: Any) -> Any:
        self.span_calls.append(kwargs)
        return _pages(self._spans, self._error)

    def _list_traces(self, **kwargs: Any) -> Any:
        self.trace_calls.append(kwargs)
        wanted = set(kwargs["filter"]["id"]["$in"])
        return _pages([row for row in self._summaries if row.id in wanted], None)


def _client(
    spans: list[SimpleNamespace] | None = None,
    summaries: list[SimpleNamespace] | None = None,
    error: Exception | None = None,
) -> Any:
    """A fake platform client, typed ``Any`` so call sites need no cast."""
    return _FakeClient(spans or [], summaries or [], error)


def _status_error(code: int) -> APIStatusError:
    request = httpx.Request("GET", "https://example.invalid/spans")
    return APIStatusError("boom", response=httpx.Response(code, request=request), body=None)


async def test_scan_dedupes_trace_ids_and_orders_newest_first() -> None:
    # Interleaved on purpose: one trace id must produce one entry, whichever order
    # its spans arrive in.
    client = _client(
        spans=[
            _span("t-new", minute=50),
            _span("t-old", minute=20),
            _span("t-new", minute=40),
            _span("t-old", minute=10),
        ],
        summaries=[_summary("t-new", minute=40), _summary("t-old", minute=10)],
    )

    result = await traces.list_traces(client, agent="aut", workspace="ws")

    assert [trace["trace_ref"] for trace in result["traces"]] == ["intake://t-new", "intake://t-old"]
    assert result["count"] == 2
    assert result["truncated"] is False
    assert result["traces"][0]["started_at"] == _at(40).isoformat()


async def test_server_summary_overrides_the_scanned_window() -> None:
    # The scan sees two spans and no error. The server knows the trace holds 40 spans
    # and three errors. Counting from the window alone would report a healthy trace.
    client = _client(
        spans=[_span("t-1", minute=50, tool_name="search"), _span("t-1", minute=49, model="gpt")],
        summaries=[
            _summary("t-1", minute=10, status="error", span_count=40, error_count=3, name="run", duration_ms=99.5)
        ],
    )

    result = await traces.list_traces(client, agent="aut", workspace="ws")

    trace = result["traces"][0]
    assert trace["status"] == "error"
    assert trace["span_count"] == 40
    assert trace["error_count"] == 3
    assert trace["name"] == "run"
    assert trace["duration_ms"] == 99.5
    assert trace["started_at"] == _at(10).isoformat()
    assert client.trace_calls[0]["filter"] == {"id": {"$in": ["t-1"]}}


async def test_missing_summary_falls_back_to_the_scan() -> None:
    # A trace whose root span was never ingested has no traces.list row. It must still
    # be returned, and its unknown fields must not read as zero.
    client = _client(spans=[_span("t-1", minute=30)], summaries=[])

    result = await traces.list_traces(client, agent="aut", workspace="ws")

    trace = result["traces"][0]
    assert trace["trace_ref"] == "intake://t-1"
    assert trace["status"] == "unknown"
    assert trace["span_count"] is None
    assert trace["error_count"] is None
    assert trace["started_at"] == _at(30).isoformat()


async def test_trace_ids_are_chunked() -> None:
    spans = [_span(f"t-{index}", minute=index) for index in range(120)]
    client = _client(spans=spans, summaries=[_summary(f"t-{index}", minute=index) for index in range(120)])

    result = await traces.list_traces(client, agent="aut", workspace="ws", limit=120, span_budget=200)

    assert result["count"] == 120
    assert [len(call["filter"]["id"]["$in"]) for call in client.trace_calls] == [50, 50, 20]


async def test_span_budget_truncates() -> None:
    client = _client(spans=[_span(f"t-{index}", minute=index) for index in range(10)])

    result = await traces.list_traces(client, agent="aut", workspace="ws", span_budget=4)

    assert result["count"] == 4
    assert result["truncated"] is True


async def test_limit_truncates_and_clamps_page_size() -> None:
    client = _client(spans=[_span(f"t-{index}", minute=index) for index in range(10)])

    result = await traces.list_traces(client, agent="aut", workspace="ws", limit=3)

    assert result["count"] == 3
    assert result["truncated"] is True
    assert client.span_calls[0]["page_size"] <= 100


async def test_since_reaches_the_filter() -> None:
    client = _client()
    since = _at(30)

    await traces.list_traces(client, agent="aut", workspace="ws", since=since)

    assert client.span_calls[0]["filter"] == {"agent_name": "aut", "started_at": {"gte": since.isoformat()}}
    assert client.span_calls[0]["sort"] == "-started_at"


async def test_empty_result_is_not_an_error() -> None:
    client = _client()

    result = await traces.list_traces(client, agent="typo-agent", workspace="ws")

    assert result["count"] == 0
    assert "typo-agent" in result["note"]
    assert "ws" in result["note"]
    # Nothing to summarize, so the second call must not be made.
    assert client.trace_calls == []


async def test_facets_count_traces() -> None:
    client = _client(
        spans=[
            _span("t-1", minute=50, error_type="Timeout", tool_name="search", model="gpt"),
            _span("t-1", minute=49, tool_name="search", model="gpt"),
            _span("t-2", minute=30, tool_name="fetch", model="gpt"),
        ],
        summaries=[
            _summary("t-1", minute=49, status="error", error_count=1),
            _summary("t-2", minute=30),
        ],
    )

    result = await traces.list_traces(client, agent="aut", workspace="ws")

    assert result["traces"][0]["tool"] == ["search"]
    assert traces.facets(result, "status") == {"error": 1, "success": 1}
    assert traces.facets(result, "model") == {"gpt": 2}
    assert traces.facets(result, "tool") == {"search": 1, "fetch": 1}
    assert traces.facets(result, "error_type") == {"Timeout": 1}


def test_unknown_facet_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported facet"):
        traces.facets({"traces": []}, "kind")


async def test_auth_failure_says_how_to_recover() -> None:
    client = _client(error=_status_error(401))

    with pytest.raises(traces.TraceQueryError, match="nemo auth login"):
        await traces.list_traces(client, agent="aut", workspace="ws")


async def test_unreachable_platform_names_the_base_url() -> None:
    request = httpx.Request("GET", "https://example.invalid/spans")
    client = _client(error=APIConnectionError(request=request))

    with pytest.raises(traces.TraceQueryError, match="NMP_BASE_URL"):
        await traces.list_traces(client, agent="aut", workspace="ws")


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
        await eval_author.list_traces("aut")


async def test_agent_trace_tools_delegate() -> None:
    client = _client(
        spans=[_span("t-1", minute=10, tool_name="search")],
        summaries=[_summary("t-1", minute=10, span_count=7)],
    )
    eval_author = _agent(client, "ws")

    result = await eval_author.list_traces("aut")

    assert result["traces"][0]["trace_ref"] == "intake://t-1"
    assert result["traces"][0]["span_count"] == 7
    assert eval_author.facets(result, "tool") == {"search": 1}
