# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query-plugin framework + optional local plugin tests."""

from typing import Any, ClassVar, cast

import pytest
from nmp.intake.query_plugins.base import QueryPlugin
from nmp.intake.query_plugins.context import QueryPluginContext
from nmp.intake.query_plugins.registry import QUERY_PLUGINS, get_query_plugin, query_plugin_ids
from nmp.intake.query_plugins.runner import QueryPluginRunner
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from pydantic import BaseModel


class _EchoOutput(BaseModel):
    value: str


class _EchoQueryPlugin(QueryPlugin):
    id: ClassVar[str] = "test-echo"
    output_model: ClassVar[type[BaseModel]] = _EchoOutput

    def build_query(self, ctx: QueryPluginContext) -> tuple[str, dict[str, Any]]:
        return "SELECT %(value)s AS value", {"value": ctx.workspace}

    def parse(self, rows: list[dict[str, Any]]) -> _EchoOutput:
        return _EchoOutput(value=str(rows[0]["value"]))


class _QueryResult:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str]) -> None:
        self.result_rows = rows
        self.column_names = columns


class _Client:
    def __init__(self, query_results: list[_QueryResult]) -> None:
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self.query_results = query_results

    def table(self, name: str) -> str:
        return f"intake.{name}"

    async def query(self, query: str, *, parameters: dict[str, object]) -> _QueryResult:
        self.queries.append(query)
        self.parameters.append(parameters)
        return self.query_results.pop(0)


def test_registry_lists_deployed_plugins_with_unique_ids():
    ids = query_plugin_ids()
    assert len(ids) == len(set(ids))
    assert all(plugin.id for plugin in QUERY_PLUGINS)
    for plugin_id in ids:
        assert get_query_plugin(plugin_id) is not None
    assert get_query_plugin("does-not-exist") is None


def test_run_query_plugin_endpoint_returns_404_for_unknown_plugin(client):
    response = client.get(
        "/apis/intake/v2/workspaces/default/query-plugins/does-not-exist",
        params={"experiment_id": "exp-a"},
    )
    assert response.status_code == 404


def test_run_query_plugin_endpoint_returns_503_without_clickhouse(client):
    plugin_id = query_plugin_ids()[0] if query_plugin_ids() else "experiment-error-summary"
    response = client.get(
        f"/apis/intake/v2/workspaces/default/query-plugins/{plugin_id}",
        params={"experiment_id": "exp-a"},
    )
    assert response.status_code in {404, 503}


def test_list_query_plugins_endpoint(client):
    response = client.get("/apis/intake/v2/workspaces/default/query-plugins")
    assert response.status_code == 200
    payload = response.json()
    assert "query_plugins" in payload
    assert all("id" in item for item in payload["query_plugins"])

    ids = query_plugin_ids()
    assert len(ids) == len(set(ids))
    assert all(plugin.id for plugin in QUERY_PLUGINS)
    for plugin_id in ids:
        assert get_query_plugin(plugin_id) is not None
    assert get_query_plugin("does-not-exist") is None


@pytest.mark.asyncio
async def test_runner_executes_plugin_with_qualified_tables():
    client = _Client([_QueryResult([("default",)], ["value"])])
    runner = QueryPluginRunner(cast(ClickHouseSpanClient, client))

    result = cast(_EchoOutput, await runner.run(_EchoQueryPlugin(), workspace="default"))

    assert result.value == "default"
    assert client.queries == ["SELECT %(value)s AS value"]
    assert client.parameters[0]["value"] == "default"


def _require_experiment_error_plugins():
    summary = get_query_plugin("experiment-error-summary")
    spans = get_query_plugin("experiment-error-spans")
    if summary is None or spans is None:
        pytest.skip("experiment error query plugins not registered (see query_plugins/custom/README.md)")
    return summary, spans


def test_experiment_error_plugins_are_registered_when_deployed_locally():
    if not get_query_plugin("experiment-error-summary"):
        pytest.skip("local query plugins not configured")
    assert query_plugin_ids() == ["experiment-error-summary", "experiment-error-spans"]


def test_build_query_scopes_to_experiment_and_error_spans():
    from nmp.intake.query_plugins.custom.experiment_error_summary import (
        UNSPECIFIED_ERROR_TYPE,
        ExperimentErrorSummaryQueryPlugin,
    )

    _require_experiment_error_plugins()
    plugin = ExperimentErrorSummaryQueryPlugin()
    ctx = QueryPluginContext(workspace="default", experiment_ids=("exp-a", "exp-a", "exp-b"))

    sql, parameters = plugin.build_query(ctx)

    assert "FROM trace_index FINAL" in sql
    assert "experiment_id IN (%(experiment_id_0)s, %(experiment_id_1)s)" in sql
    assert "(span_versions.workspace, span_versions.session_id) IN" in sql
    assert "spans.status = 'error'" in sql
    assert "GROUP BY error_type" in sql
    assert "ORDER BY count DESC, error_type ASC" in sql

    assert parameters["workspace"] == "default"
    assert parameters["experiment_id_0"] == "exp-a"
    assert parameters["experiment_id_1"] == "exp-b"
    assert "experiment_id_2" not in parameters
    assert parameters["error_type_key"] == "exception.type"
    assert parameters["unspecified_error_type"] == UNSPECIFIED_ERROR_TYPE


def test_parse_totals_counts_and_preserves_query_order():
    from nmp.intake.query_plugins.custom.experiment_error_summary import (
        UNSPECIFIED_ERROR_TYPE,
        ErrorTypeCount,
        ExperimentErrorSummary,
        ExperimentErrorSummaryQueryPlugin,
    )

    _require_experiment_error_plugins()
    plugin = ExperimentErrorSummaryQueryPlugin()

    summary = plugin.parse(
        [
            {"error_type": "llm_rate_limit", "count": 4},
            {"error_type": "tool_timeout", "count": 2},
            {"error_type": UNSPECIFIED_ERROR_TYPE, "count": 1},
        ]
    )

    assert summary.total_error_spans == 7
    assert [(row.error_type, row.count) for row in summary.rows] == [
        ("llm_rate_limit", 4),
        ("tool_timeout", 2),
        (UNSPECIFIED_ERROR_TYPE, 1),
    ]


def test_parse_returns_empty_summary_for_no_error_spans():
    from nmp.intake.query_plugins.custom.experiment_error_summary import (
        ExperimentErrorSummary,
        ExperimentErrorSummaryQueryPlugin,
    )

    _require_experiment_error_plugins()
    summary = ExperimentErrorSummaryQueryPlugin().parse([])
    assert summary == ExperimentErrorSummary(total_error_spans=0, rows=[])


@pytest.mark.asyncio
async def test_summary_runner_executes_with_qualified_tables():
    from nmp.intake.query_plugins.custom.experiment_error_summary import (
        ErrorTypeCount,
        ExperimentErrorSummary,
        ExperimentErrorSummaryQueryPlugin,
    )

    _require_experiment_error_plugins()
    client = _Client([_QueryResult([("tool_timeout", 3)], ["error_type", "count"])])
    runner = QueryPluginRunner(cast(ClickHouseSpanClient, client))

    summary = cast(
        ExperimentErrorSummary,
        await runner.run(
            ExperimentErrorSummaryQueryPlugin(),
            workspace="default",
            experiment_ids=["exp-a"],
        ),
    )

    assert summary.total_error_spans == 3
    assert summary.rows == [ErrorTypeCount(error_type="tool_timeout", count=3)]
    assert "FROM intake.trace_index FINAL" in client.queries[0]
    assert client.parameters[0]["experiment_id_0"] == "exp-a"


def test_error_spans_build_query_scopes_to_experiment_and_error_spans():
    from nmp.intake.query_plugins.custom.experiment_error_spans import (
        ERROR_SPANS_LIMIT,
        ExperimentErrorSpansQueryPlugin,
    )
    from nmp.intake.query_plugins.custom.experiment_error_summary import UNSPECIFIED_ERROR_TYPE

    _require_experiment_error_plugins()
    plugin = ExperimentErrorSpansQueryPlugin()
    ctx = QueryPluginContext(workspace="default", experiment_ids=("exp-a", "exp-b"))

    sql, parameters = plugin.build_query(ctx)

    assert "FROM trace_index FINAL" in sql
    assert "experiment_id IN (%(experiment_id_0)s, %(experiment_id_1)s)" in sql
    assert "spans.status = 'error'" in sql
    assert "ORDER BY spans.start_time DESC, spans.id ASC" in sql
    assert f"LIMIT {ERROR_SPANS_LIMIT}" in sql

    assert parameters["workspace"] == "default"
    assert parameters["error_type_key"] == "exception.type"
    assert parameters["error_message_key"] == "exception.message"
    assert parameters["unspecified_error_type"] == UNSPECIFIED_ERROR_TYPE


def test_error_spans_parse_flattens_rows_and_falls_back_for_blank_error_type():
    from nmp.intake.query_plugins.custom.experiment_error_spans import (
        ErrorSpan,
        ExperimentErrorSpans,
        ExperimentErrorSpansQueryPlugin,
    )
    from nmp.intake.query_plugins.custom.experiment_error_summary import UNSPECIFIED_ERROR_TYPE

    _require_experiment_error_plugins()
    plugin = ExperimentErrorSpansQueryPlugin()

    result = plugin.parse(
        [
            {
                "span_id": "span-1",
                "trace_id": "trace-1",
                "session_id": "sess-1",
                "name": "call_tool",
                "error_type": "tool_timeout",
                "error_message": "timed out after 30s",
                "status": "error",
                "start_time": None,
            },
            {
                "span_id": "span-2",
                "trace_id": "trace-2",
                "session_id": "",
                "name": "",
                "error_type": "",
                "error_message": "",
                "status": "error",
                "start_time": None,
            },
        ]
    )

    assert result.total == 2
    assert result.spans[0] == ErrorSpan(
        span_id="span-1",
        trace_id="trace-1",
        session_id="sess-1",
        name="call_tool",
        error_type="tool_timeout",
        error_message="timed out after 30s",
        status="error",
    )
    assert result.spans[1].session_id is None
    assert result.spans[1].name is None
    assert result.spans[1].error_message is None
    assert result.spans[1].error_type == UNSPECIFIED_ERROR_TYPE


def test_error_spans_parse_returns_empty_for_no_rows():
    from nmp.intake.query_plugins.custom.experiment_error_spans import (
        ExperimentErrorSpans,
        ExperimentErrorSpansQueryPlugin,
    )

    _require_experiment_error_plugins()
    assert ExperimentErrorSpansQueryPlugin().parse([]) == ExperimentErrorSpans(total=0, spans=[])
