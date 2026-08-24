# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Behavior tests for the Eval Author Intake trace source."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
_INSPECT_SCRIPTS = _SKILLS_DIR / "eval-author-inspect-trace" / "scripts"
_INTAKE_DIR = _INSPECT_SCRIPTS / "sources" / "intake"
_INSPECT = _INSPECT_SCRIPTS / "inspect_trace.py"
_MODULE_PATHS = (
    *(_INTAKE_DIR / name for name in ("_http.py", "traces.py", "reader.py")),
    _INSPECT_SCRIPTS / "overview.py",
)


def _modules() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    """Load the wished-for public modules after asserting their paths exist."""
    missing = [path.name for path in _MODULE_PATHS if not path.exists()]
    assert not missing, f"missing Intake modules: {missing}"
    if str(_INTAKE_DIR) not in sys.path:
        sys.path.insert(0, str(_INTAKE_DIR))
    if str(_INSPECT_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_INSPECT_SCRIPTS))
    modules = [importlib.import_module(name) for name in ("_http", "traces", "reader", "overview")]
    return modules[0], modules[1], modules[2], modules[3]


def _page(
    data: list[dict],
    *,
    page: int = 1,
    total_pages: int = 1,
    total_results: int | None = None,
    page_size: int = 100,
) -> dict:
    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "current_page_size": len(data),
            "total_pages": total_pages,
            "total_results": len(data) if total_results is None else total_results,
        },
    }


class _Scenario:
    def __init__(self) -> None:
        self.responses: deque[tuple[int, dict | None, dict[str, str]]] = deque()
        self.requests: list[dict] = []

    def respond(self, body: dict, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.responses.append((status, body, headers or {}))

    def redirect(self, location: str) -> None:
        self.responses.append((302, None, {"Location": location}))


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"

    def do_GET(self) -> None:  # noqa: N802
        scenario = self.server.scenario
        scenario.requests.append({"path": self.path, "authorization": self.headers.get("Authorization")})
        status, body, headers = scenario.responses.popleft()
        payload = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        if body is not None:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _Server(ThreadingHTTPServer):
    scenario: _Scenario


@contextmanager
def _api() -> Iterator[tuple[str, _Scenario]]:
    scenario = _Scenario()
    server = _Server(("127.0.0.1", 0), _Handler)
    server.scenario = scenario
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", scenario
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _query(request: dict) -> dict[str, list[str]]:
    return parse_qs(urlsplit(request["path"]).query)


def test_intake_source_modules_exist_and_import_without_the_platform() -> None:
    http, traces, reader, overview = _modules()

    assert http.IntakeClient
    assert traces.query_spans
    assert reader.read_trace
    assert overview.build_overview


@pytest.mark.parametrize(
    ("base_url", "message"),
    [
        ("http://platform.example.com", "HTTPS"),
        ("https://name:secret@platform.example.com", "userinfo"),  # trufflehog:ignore
        ("ftp://platform.example.com", "HTTPS"),
    ],
)
def test_client_rejects_unsafe_platform_origins(base_url: str, message: str) -> None:
    http, *_ = _modules()

    with pytest.raises(ValueError, match=message):
        http.IntakeClient(base_url, "default")


def test_span_query_encodes_nested_filters_and_bearer_auth() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(_page([{"span_id": "span-1", "trace_id": "trace-1"}]))
        client = http.IntakeClient(base_url, "space/name", access_token="secret")

        result = traces.query_spans(
            client,
            filter={"agent_name": "support", "started_at": {"gte": "2026-01-01T00:00:00+00:00"}},
        )

    request = scenario.requests[0]
    assert urlsplit(request["path"]).path == "/apis/intake/v2/workspaces/space%2Fname/spans"
    assert request["authorization"] == "Bearer secret"
    assert _query(request)["filter[agent_name]"] == ["support"]
    assert _query(request)["filter[started_at][gte]"] == ["2026-01-01T00:00:00+00:00"]
    assert result["spans"][0]["trace_ref"] == "intake://trace-1"


def test_authenticated_requests_do_not_follow_redirects() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.redirect(f"{base_url}/elsewhere")
        client = http.IntakeClient(base_url, "default", access_token="secret")

        with pytest.raises(http.IntakeError, match="redirect"):
            traces.query_spans(client)

    assert len(scenario.requests) == 1


@pytest.mark.parametrize(
    ("status", "guidance"),
    [(401, "NMP_ACCESS_TOKEN"), (404, "workspace"), (400, "filter")],
)
def test_http_errors_include_actionable_guidance(status: int, guidance: str) -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond({"detail": "bad request"}, status=status)

        with pytest.raises(http.IntakeError, match=guidance):
            traces.query_spans(http.IntakeClient(base_url, "default"))


def test_span_query_drains_pages_and_reports_truncation() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(
            _page(
                [{"span_id": "span-1"}, {"span_id": "span-2"}],
                page=1,
                total_pages=2,
                total_results=4,
                page_size=2,
            )
        )
        scenario.respond(
            _page(
                [{"span_id": "span-3"}, {"span_id": "span-4"}],
                page=2,
                total_pages=2,
                total_results=4,
                page_size=2,
            )
        )

        result = traces.query_spans(http.IntakeClient(base_url, "default"), limit=3)

    assert [row["span_id"] for row in result["spans"]] == ["span-1", "span-2", "span-3"]
    assert result["truncated"] is True
    assert [_query(request)["page"] for request in scenario.requests] == [["1"], ["2"]]


def test_grouped_span_query_preserves_the_server_group() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(_page([{"group": {"trace_id": "trace-1"}, "span_count": 3}]))

        result = traces.query_spans(
            http.IntakeClient(base_url, "default"),
            filter={"tool_name": "search"},
            group_by="trace_id",
            sort="-span_count",
        )

    request = scenario.requests[0]
    assert urlsplit(request["path"]).path.endswith("/spans/groups")
    assert _query(request)["by"] == ["trace_id"]
    assert _query(request)["sort"] == ["-span_count"]
    assert result == {
        "groups": [{"group": {"trace_id": "trace-1"}, "span_count": 3, "trace_ref": "intake://trace-1"}],
        "grouped_by": "trace_id",
        "count": 1,
        "truncated": False,
    }


def test_trace_query_requests_preview_rollups() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(_page([{"id": "trace-1", "span_count": 8, "error_count": 1}]))

        result = traces.query_traces(
            http.IntakeClient(base_url, "default"),
            filter={"id": {"$in": ["trace-1"]}},
        )

    assert _query(scenario.requests[0])["mode"] == ["preview"]
    assert _query(scenario.requests[0])["filter[id][$in]"] == ["trace-1"]
    assert result["traces"][0]["error_count"] == 1


@pytest.mark.parametrize("values", [[], [None], [{}]], ids=("empty", "null-only", "empty-object"))
def test_empty_sequence_filters_are_rejected_instead_of_removed(values: list[Any]) -> None:
    http, *_ = _modules()

    with pytest.raises(ValueError, match="must not be empty"):
        http.encode_query({"filter": {"id": {"$in": values}}})


def test_find_agent_traces_merges_summaries_without_hiding_unknowns() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(
            _page(
                [
                    {"group": {"trace_id": "trace-old"}, "span_count": 1},
                    {"group": {"trace_id": "trace-missing"}, "span_count": 1},
                    {"group": {"trace_id": "trace-new"}, "span_count": 1},
                ]
            )
        )
        scenario.respond(
            _page(
                [
                    {"id": "trace-old", "started_at": "2026-01-01T00:00:00Z", "status": "success"},
                    {"id": "trace-new", "started_at": "2026-01-03T00:00:00Z", "status": "error"},
                ]
            )
        )

        result = traces.find_agent_traces(http.IntakeClient(base_url, "default"), "support")

    assert [row["trace_id"] for row in result["traces"]] == ["trace-new", "trace-old", "trace-missing"]
    assert result["traces"][-1]["status"] == "unknown"
    assert result["traces"][-1]["span_count"] is None
    assert _query(scenario.requests[0])["filter[agent_name]"] == ["support"]


def test_find_agent_traces_chunks_summary_queries_at_fifty_ids() -> None:
    http, traces, *_ = _modules()
    groups: list[dict[str, Any]] = [
        {"group": {"trace_id": f"trace-{index:02}"}, "span_count": 1} for index in range(51)
    ]
    with _api() as (base_url, scenario):
        scenario.respond(_page(groups))
        scenario.respond(_page([{"id": row["group"]["trace_id"]} for row in groups[:50]]))
        scenario.respond(_page([{"id": groups[-1]["group"]["trace_id"]}]))

        result = traces.find_agent_traces(http.IntakeClient(base_url, "default"), "support", limit=51)

    trace_requests = scenario.requests[1:]
    assert result["count"] == 51
    assert [len(_query(request)["filter[id][$in]"]) for request in trace_requests] == [50, 1]


def test_an_empty_agent_query_does_not_request_trace_summaries() -> None:
    http, traces, *_ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(_page([]))

        result = traces.find_agent_traces(http.IntakeClient(base_url, "default"), "missing")

    assert result["count"] == 0
    assert "missing" in result["note"]
    assert len(scenario.requests) == 1


@pytest.mark.parametrize("ref", ["trace-1", "intake://trace-1", "intake://traces/trace-1"])
def test_read_trace_normalizes_refs_and_fetches_all_evidence(ref: str) -> None:
    http, _, reader, _ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(_page([{"id": "trace-1", "status": "success", "error_count": 1}]))
        scenario.respond(
            _page(
                [
                    {
                        "span_id": "span-2",
                        "trace_id": "trace-1",
                        "session_id": "session-2",
                        "started_at": "2026-01-01T00:00:02Z",
                        "status": "success",
                        "kind": "TOOL",
                    },
                    {
                        "span_id": "span-1",
                        "trace_id": "trace-1",
                        "session_id": "session-1",
                        "started_at": "2026-01-01T00:00:01Z",
                        "status": "error",
                        "kind": "LLM",
                    },
                ]
            )
        )
        scenario.respond(
            _page(
                [
                    {"evaluator_result_id": "eval-1", "span_id": "span-1", "session_id": "session-1"},
                    {"evaluator_result_id": "other-trace", "span_id": "other-span", "session_id": "session-1"},
                ]
            )
        )
        scenario.respond(_page([{"evaluator_result_id": "eval-2", "span_id": "span-2", "session_id": "session-2"}]))

        result = reader.read_trace(http.IntakeClient(base_url, "default"), ref)

    assert result["trace_id"] == "trace-1"
    assert result["trace_ref"] == "intake://trace-1"
    assert result["session_ids"] == ["session-1", "session-2"]
    assert [span["span_id"] for span in result["spans"]] == ["span-1", "span-2"]
    assert [item["evaluator_result_id"] for item in result["evaluator_results"]] == ["eval-1", "eval-2"]
    assert _query(scenario.requests[1])["mode"] == ["detailed"]
    assert _query(scenario.requests[1])["sort"] == ["started_at"]


def test_read_trace_rejects_a_trace_with_no_spans() -> None:
    http, _, reader, _ = _modules()
    with _api() as (base_url, scenario):
        scenario.respond(_page([]))
        scenario.respond(_page([]))

        with pytest.raises(http.IntakeError, match="No spans"):
            reader.read_trace(http.IntakeClient(base_url, "default"), "missing")


@pytest.mark.parametrize(
    ("summary", "spans", "expected"),
    [
        (
            {"status": "success", "duration_ms": 10},
            [{"span_id": "one", "status": "success", "kind": "AGENT", "session_id": "s"}],
            {"root_status": "success", "error_span_count": 0, "root_succeeded_with_errors": False},
        ),
        (
            {"status": "error", "duration_ms": 10},
            [{"span_id": "one", "status": "error", "kind": "AGENT", "session_id": "s"}],
            {"root_status": "error", "error_span_count": 1, "root_succeeded_with_errors": False},
        ),
        (
            {"status": "success", "duration_ms": 10},
            [
                {"span_id": "one", "status": "error", "kind": "TOOL", "session_id": "s"},
                {"span_id": "two", "status": "success", "kind": "AGENT", "session_id": "s"},
            ],
            {"root_status": "success", "error_span_count": 1, "root_succeeded_with_errors": True},
        ),
        (
            {"status": "error", "duration_ms": 10},
            [
                {"span_id": "one", "status": "success", "kind": "TOOL", "session_id": "s"},
                {"span_id": "two", "status": "error", "kind": "AGENT", "session_id": "s"},
            ],
            {"root_status": "error", "error_span_count": 1, "root_succeeded_with_errors": False},
        ),
        (
            None,
            [{"span_id": "one", "status": "unknown", "kind": "CHAIN", "session_id": "s"}],
            {"root_status": "unknown", "error_span_count": 0, "root_succeeded_with_errors": False},
        ),
    ],
    ids=("successful", "failed", "recovered", "mixed", "incomplete"),
)
def test_overview_reports_facts_without_classifying_the_trace(
    summary: dict | None,
    spans: list[dict],
    expected: dict,
) -> None:
    *_, overview = _modules()
    bundle = {
        "trace_id": "trace-1",
        "trace_ref": "intake://trace-1",
        "summary": summary,
        "session_ids": ["s"],
        "spans": spans,
        "evaluator_results": [],
    }

    result = overview.build_overview(bundle)

    assert {name: result[name] for name in expected} == expected
    assert "classification" not in result
    assert result["status_counts"] == {
        status: sum(span["status"] == status for span in spans) for status in sorted({span["status"] for span in spans})
    }


def test_overview_accepts_null_trace_rollup_lists() -> None:
    *_, overview = _modules()
    bundle = {
        "trace_id": "trace-1",
        "trace_ref": "intake://trace-1",
        "summary": {"status": "success", "models": None, "providers": None},
        "session_ids": [],
        "spans": [],
        "evaluator_results": [],
    }

    result = overview.build_overview(bundle)

    assert result["models"] == []
    assert result["providers"] == []


def test_overview_fallback_duration_uses_the_latest_span_end() -> None:
    *_, overview = _modules()
    bundle = {
        "trace_id": "trace-1",
        "trace_ref": "intake://trace-1",
        "summary": None,
        "session_ids": ["session-1"],
        "spans": [
            {
                "span_id": "long",
                "session_id": "session-1",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:10:00Z",
                "status": "success",
            },
            {
                "span_id": "short",
                "session_id": "session-1",
                "started_at": "2026-01-01T00:02:00Z",
                "ended_at": "2026-01-01T00:03:00Z",
                "status": "success",
            },
        ],
        "evaluator_results": [],
    }

    result = overview.build_overview(bundle)

    assert result["root_duration_ms"] == 600_000


def test_overview_separates_cancelled_spans_from_incomplete_telemetry() -> None:
    *_, overview = _modules()
    bundle = {
        "trace_id": "trace-1",
        "trace_ref": "intake://trace-1",
        "summary": {"status": "cancelled"},
        "session_ids": ["session-1"],
        "spans": [
            {
                "span_id": "cancelled",
                "session_id": "session-1",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:00:01Z",
                "status": "cancelled",
            }
        ],
        "evaluator_results": [],
    }

    result = overview.build_overview(bundle)

    assert result["cancelled_span_ids"] == ["cancelled"]
    assert result["incomplete_span_ids"] == []


@pytest.mark.parametrize("trace_ref", ["trace-1", "intake:trace-1"], ids=("bare", "missing-slashes"))
def test_inspect_entry_point_rejects_an_unqualified_trace_reference(trace_ref: str) -> None:
    env = {key: value for key, value in os.environ.items() if key not in {"NMP_BASE_URL", "NMP_ACCESS_TOKEN"}}

    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(_INSPECT),
            "--workspace",
            "default",
            "--trace",
            trace_ref,
            "--compact",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert "source-qualified" in report["error"]
    assert report["supported_sources"] == ["intake"]


def test_inspect_entry_point_rejects_an_unknown_trace_source() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(_INSPECT),
            "--workspace",
            "default",
            "--trace",
            "langfuse://project/trace-1",
            "--compact",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert "langfuse" in report["error"]
    assert report["supported_sources"] == ["intake"]
    assert "NMP_" not in report["hint"]


@pytest.mark.parametrize(
    ("trace_id", "workspace"),
    [
        ("trace-1", "default"),
        ("trace-1", "other-workspace"),
        ("../../README", "default"),
        ("x" * 512, "default"),
    ],
    ids=("regular", "other-workspace", "path-traversal", "long"),
)
def test_inspect_entry_point_emits_json_and_writes_nothing(
    tmp_path: Path,
    trace_id: str,
    workspace: str,
) -> None:
    assert _INSPECT.exists(), "missing inspect_trace.py"
    shadow_package = tmp_path / "site-packages" / "intake"
    shadow_package.mkdir(parents=True)
    (shadow_package / "__init__.py").write_text("", encoding="utf-8")
    with _api() as (base_url, scenario):
        scenario.respond(_page([{"id": trace_id, "status": "success", "error_count": 0}]))
        scenario.respond(
            _page(
                [
                    {
                        "span_id": "span-1",
                        "trace_id": trace_id,
                        "session_id": "session-1",
                        "started_at": "2026-01-01T00:00:00Z",
                        "status": "success",
                        "kind": "AGENT",
                    }
                ]
            )
        )
        scenario.respond(_page([]))
        env = {**os.environ, "NMP_BASE_URL": base_url, "NMP_ACCESS_TOKEN": "secret"}
        env["PYTHONPATH"] = os.pathsep.join(
            value for value in (str(shadow_package.parent), env.get("PYTHONPATH")) if value
        )
        before = list(tmp_path.iterdir())

        result = subprocess.run(
            [
                sys.executable,
                "-S",
                str(_INSPECT),
                "--workspace",
                workspace,
                "--trace",
                f"intake://traces/{trace_id}",
                "--compact",
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == "1"
    assert report["trace"]["trace_id"] == trace_id
    assert report["source"] == {
        "kind": "intake",
        "trace_ref": f"intake://{trace_id}",
        "context": {"platform_origin": base_url, "workspace": workspace},
    }
    identity = json.dumps(report["source"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert "platform_origin" not in report
    assert "workspace" not in report
    assert report["report_path"] == f".eval-author/traces/{hashlib.sha256(identity.encode()).hexdigest()}.md"
    assert report["overview"]["root_status"] == "success"
    assert scenario.requests[0]["authorization"] == "Bearer secret"
    assert list(tmp_path.iterdir()) == before
