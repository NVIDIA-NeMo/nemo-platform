# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake trace reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import IntakeTrace, TraceListFilter, TraceMode
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field
from nmp.intake.spans.storage import float_or_none, int_or_none, make_pagination, normalize_span_status, result_rows

TRACE_SORT_COLUMNS = {
    "started_at": "started_at",
}

METRIC_ATTRIBUTE_FIELDS = {
    "input_tokens": SpanAttributeField.INPUT_TOKENS,
    "output_tokens": SpanAttributeField.OUTPUT_TOKENS,
    "cached_tokens": SpanAttributeField.CACHED_TOKENS,
    "total_tokens": SpanAttributeField.TOTAL_TOKENS,
    "cost_usd": SpanAttributeField.COST_TOTAL_USD,
    "cost_input_usd": SpanAttributeField.COST_INPUT_USD,
    "cost_output_usd": SpanAttributeField.COST_OUTPUT_USD,
}

TRACE_COLUMNS = [
    "id",
    "workspace",
    "session_id",
    "source_format",
    "root_span_id",
    "name",
    "input",
    "output",
    "project",
    "experiment_id",
    "test_case_id",
    "started_at",
    "ended_at",
    "status",
    *METRIC_ATTRIBUTE_FIELDS.keys(),
    "models",
    "providers",
    "span_count",
    "error_count",
    "ingested_at",
]

_CURRENT_SPAN_IDENTITY_COLUMNS = (
    "workspace",
    "source_format",
    "trace_id",
    "external_span_id",
    "id",
)
_CURRENT_SPAN_VALUE_COLUMNS = (
    "session_id",
    "external_parent_span_id",
    "kind",
    "name",
    "status",
    "start_time",
    "end_time",
    "attributes_string",
    "attributes_number",
    "attributes_bool",
    "input",
    "output",
    "event_ts",
    "is_deleted",
)

_ZERO_DATETIME = datetime.fromtimestamp(0, tz=timezone.utc)


class TraceRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._client = client

    async def list_traces(
        self,
        *,
        filters: TraceListFilter,
        page: int,
        page_size: int,
        sort: str,
        mode: TraceMode,
    ) -> PaginatedResult[IntakeTrace]:
        trace_index_table = self._client.table("trace_index")
        spans_table = self._client.table("spans")
        trace_index_sql, parameters = _trace_index_sql(trace_index_table, filters)

        total_result = await self._client.query(
            f"""
            SELECT count()
            FROM ({trace_index_sql}) AS traces
            """,
            parameters=parameters,
        )
        total_results = int(total_result.result_rows[0][0])

        offset = (page - 1) * page_size
        rows_sql, rows_parameters = _trace_rows_sql(
            trace_index_sql=trace_index_sql,
            spans_table=spans_table,
            mode=mode,
            sort=sort,
        )
        rows_result = await self._client.query(
            rows_sql,
            parameters={**parameters, **rows_parameters, "limit": page_size, "offset": offset},
        )
        rows = result_rows(rows_result)
        traces = [_row_to_trace(row) for row in rows]
        return PaginatedResult(
            data=traces,
            pagination=make_pagination(
                page=page,
                page_size=page_size,
                current_page_size=len(traces),
                total_results=total_results,
            ),
        )

    async def get_trace(self, *, workspace: str, trace_id: str, mode: TraceMode) -> IntakeTrace | None:
        result = await self.list_traces(
            filters=TraceListFilter(workspace=workspace, trace_id=trace_id),
            page=1,
            page_size=1,
            sort="-started_at",
            mode=mode,
        )
        return result.data[0] if result.data else None


def _trace_rows_sql(
    *, trace_index_sql: str, spans_table: str, mode: TraceMode, sort: str
) -> tuple[str, dict[str, Any]]:
    if mode == "summary":
        query = f"""
            WITH page_traces AS (
                SELECT *
                FROM ({trace_index_sql}) AS traces
                ORDER BY {_order_by(sort)}
                LIMIT %(limit)s OFFSET %(offset)s
            )
            SELECT
                {_trace_select_columns(include_aggregates=False)}
            FROM page_traces AS traces
            ORDER BY {_order_by(sort, table_alias="traces")}
        """
        return query, {}
    if mode == "detailed":
        aggregates_sql, parameters = _trace_aggregates_sql(spans_table)
        query = f"""
            WITH
            page_traces AS (
                SELECT *
                FROM ({trace_index_sql}) AS traces
                ORDER BY {_order_by(sort)}
                LIMIT %(limit)s OFFSET %(offset)s
            ),
            rollups AS (
                {aggregates_sql}
            )
            SELECT
                {_trace_select_columns(include_aggregates=True)}
            FROM page_traces AS traces
            LEFT JOIN rollups
                ON traces.workspace = rollups.workspace
                AND traces.source_format = rollups.source_format
                AND traces.id = rollups.trace_id
            ORDER BY {_order_by(sort, table_alias="traces")}
        """
        return query, parameters
    raise ValueError(f"Unsupported trace mode: {mode}")


def _trace_select_columns(*, include_aggregates: bool) -> str:
    aggregate_columns = [
        f"rollups.{column} AS {column}" if include_aggregates else f"NULL AS {column}"
        for column in (
            *METRIC_ATTRIBUTE_FIELDS.keys(),
            "models",
            "providers",
            "span_count",
            "error_count",
        )
    ]
    columns = [
        "traces.id AS id",
        "traces.workspace AS workspace",
        "traces.session_id AS session_id",
        "traces.source_format AS source_format",
        "traces.root_span_id AS root_span_id",
        "traces.name AS name",
        "traces.input AS input",
        "traces.output AS output",
        "traces.project AS project",
        "traces.experiment_id AS experiment_id",
        "traces.test_case_id AS test_case_id",
        "traces.started_at AS started_at",
        "traces.ended_at AS ended_at",
        "traces.status AS status",
        *aggregate_columns,
        "traces.ingested_at AS ingested_at",
    ]
    return ",\n            ".join(columns)


def _trace_index_sql(table: str, filters: TraceListFilter) -> tuple[str, dict[str, Any]]:
    where_sql, parameters = _trace_index_where(filters, qualifier="trace_roots")
    query = f"""
        SELECT
            trace_roots.trace_id AS id,
            trace_roots.workspace AS workspace,
            trace_roots.session_id AS session_id,
            trace_roots.source_format AS source_format,
            nullIf(trace_roots.root_span_id, '') AS root_span_id,
            nullIf(trace_roots.root_name, '') AS name,
            nullIf(trace_roots.root_input, '') AS input,
            nullIf(trace_roots.root_output, '') AS output,
            nullIf(trace_roots.project, '') AS project,
            nullIf(trace_roots.experiment_id, '') AS experiment_id,
            nullIf(trace_roots.test_case_id, '') AS test_case_id,
            trace_roots.root_started_at AS started_at,
            trace_roots.root_ended_at AS ended_at,
            trace_roots.root_status AS status,
            trace_roots.event_ts AS ingested_at
        FROM (SELECT * FROM {table} FINAL) AS trace_roots
        WHERE {where_sql}
        ORDER BY trace_roots.root_started_at ASC, trace_roots.root_span_id ASC
        LIMIT 1 BY trace_roots.workspace, trace_roots.source_format, trace_roots.trace_id
    """
    return query, parameters


def _trace_aggregates_sql(table: str) -> tuple[str, dict[str, Any]]:
    source_alias = "trace_spans"
    metric_columns, parameters = _metric_columns(source_alias)

    model_spec = spec_for_field(SpanAttributeField.MODEL)
    provider_spec = spec_for_field(SpanAttributeField.PROVIDER)
    parameters["model_key"] = model_spec.bag_key
    parameters["provider_key"] = provider_spec.bag_key

    query = f"""
        SELECT
            {source_alias}.workspace AS workspace,
            {source_alias}.source_format AS source_format,
            {source_alias}.trace_id AS trace_id,
            {metric_columns},
            arraySort(groupUniqArrayIf(
                {source_alias}.attributes_string[%(model_key)s],
                has(mapKeys({source_alias}.attributes_string), %(model_key)s)
                    AND {source_alias}.attributes_string[%(model_key)s] != ''
            )) AS models,
            arraySort(groupUniqArrayIf(
                {source_alias}.attributes_string[%(provider_key)s],
                has(mapKeys({source_alias}.attributes_string), %(provider_key)s)
                    AND {source_alias}.attributes_string[%(provider_key)s] != ''
            )) AS providers,
            count() AS span_count,
            countIf({source_alias}.status = 'error') AS error_count
        FROM {
        current_spans_sql(
            table,
            extra_where_sql=(
                "(span_versions.workspace, span_versions.source_format, span_versions.trace_id) IN "
                "(SELECT workspace, source_format, id FROM page_traces)"
            ),
        )
    } AS {source_alias}
        WHERE {source_alias}.is_deleted = 0
        GROUP BY {source_alias}.workspace, {source_alias}.source_format, {source_alias}.trace_id
    """
    return query, parameters


_TRACE_INDEX_FILTER_COLUMNS = {
    "experiment_id": "experiment_id",
    "test_case_id": "test_case_id",
}


def _trace_index_where(filters: TraceListFilter, *, qualifier: str) -> tuple[str, dict[str, Any]]:
    def column(name: str) -> str:
        return f"{qualifier}.{name}"

    clauses = [f"{column('workspace')} = %(workspace)s", f"{column('is_deleted')} = 0"]
    parameters: dict[str, Any] = {"workspace": filters.workspace}

    if filters.trace_id is not None:
        clauses.append(f"{column('trace_id')} = %(trace_id)s")
        parameters["trace_id"] = filters.trace_id
    if filters.session_id is not None:
        clauses.append(f"{column('session_id')} = %(session_id)s")
        parameters["session_id"] = filters.session_id
    if filters.source_format is not None:
        clauses.append(f"{column('source_format')} = %(source_format)s")
        parameters["source_format"] = filters.source_format
    if filters.status is not None:
        clauses.append(f"{column('root_status')} = %(status)s")
        parameters["status"] = filters.status.value
    if filters.started_at_gte is not None:
        clauses.append(f"{column('root_started_at')} >= %(started_at_gte)s")
        parameters["started_at_gte"] = filters.started_at_gte
    if filters.started_at_lte is not None:
        clauses.append(f"{column('root_started_at')} <= %(started_at_lte)s")
        parameters["started_at_lte"] = filters.started_at_lte

    for field, filter_column in _TRACE_INDEX_FILTER_COLUMNS.items():
        value = getattr(filters, field)
        if value is None:
            continue
        parameter_name = f"filter_{field}"
        clauses.append(f"{column(filter_column)} = %({parameter_name})s")
        parameters[parameter_name] = value

    return " AND ".join(clauses), parameters


def current_spans_sql(table: str, *, extra_where_sql: str | None = None) -> str:
    source_alias = "span_versions"
    columns = [
        *[f"{source_alias}.{column} AS {column}" for column in _CURRENT_SPAN_IDENTITY_COLUMNS],
        *[
            f"argMax({source_alias}.{column}, ({source_alias}.event_ts, {source_alias}.is_deleted)) AS {column}"
            for column in _CURRENT_SPAN_VALUE_COLUMNS
        ],
    ]
    columns_sql = ",\n                ".join(columns)
    group_by_sql = ", ".join(f"{source_alias}.{column}" for column in _CURRENT_SPAN_IDENTITY_COLUMNS)
    where_sql = f"{source_alias}.workspace = %(workspace)s"
    if extra_where_sql is not None:
        where_sql = f"{where_sql}\n                AND {extra_where_sql}"
    return f"""
        (
            SELECT
                {columns_sql}
            FROM {table} AS {source_alias}
            WHERE {where_sql}
            GROUP BY {group_by_sql}
        )
    """


def _metric_columns(source_alias: str) -> tuple[str, dict[str, Any]]:
    parameters: dict[str, Any] = {}
    columns: list[str] = []
    for alias, field in METRIC_ATTRIBUTE_FIELDS.items():
        spec = spec_for_field(field)
        key_param = f"{alias}_key"
        parameters[key_param] = spec.bag_key
        number_bag = f"{source_alias}.attributes_number"
        has_expr = f"has(mapKeys({number_bag}), %({key_param})s)"
        sum_expr = f"sumIf({number_bag}[%({key_param})s], {has_expr})"
        if spec.scale is not None:
            value_expr = f"{sum_expr} / {COST_SCALE}"
        else:
            value_expr = sum_expr
        columns.append(f"if(countIf({has_expr}) = 0, NULL, {value_expr}) AS {alias}")
    return ",\n            ".join(columns), parameters


def _order_by(sort: str, *, table_alias: str | None = None) -> str:
    direction = "DESC" if sort.startswith("-") else "ASC"
    field = sort.removeprefix("-")
    column = TRACE_SORT_COLUMNS.get(field)
    if column is None:
        raise ValueError(f"Unsupported trace sort field: {field}")
    if table_alias is not None:
        column = f"{table_alias}.{column}"
        id_column = f"{table_alias}.id"
    else:
        id_column = "id"
    return f"{column} {direction}, {id_column} ASC"


def _row_to_trace(row: dict[str, Any]) -> IntakeTrace:
    ended_at = _none_if_zero_datetime(row.get("ended_at"))
    return IntakeTrace(
        id=row["id"],
        root_span_id=row.get("root_span_id") or None,
        workspace=row["workspace"],
        session_id=row["session_id"],
        source_format=row["source_format"],
        name=row.get("name") or None,
        input=row.get("input") or None,
        output=row.get("output") or None,
        project=row.get("project") or None,
        experiment_id=row.get("experiment_id") or None,
        test_case_id=row.get("test_case_id") or None,
        started_at=row["started_at"],
        ended_at=ended_at,
        duration_ms=_duration_ms(row["started_at"], ended_at),
        ingested_at=row["ingested_at"],
        status=normalize_span_status(row.get("status")),
        input_tokens=int_or_none(row.get("input_tokens")),
        output_tokens=int_or_none(row.get("output_tokens")),
        cached_tokens=int_or_none(row.get("cached_tokens")),
        total_tokens=int_or_none(row.get("total_tokens")),
        cost_usd=float_or_none(row.get("cost_usd")),
        cost_input_usd=float_or_none(row.get("cost_input_usd")),
        cost_output_usd=float_or_none(row.get("cost_output_usd")),
        models=_string_list_or_none(row.get("models")),
        providers=_string_list_or_none(row.get("providers")),
        span_count=int_or_none(row.get("span_count")),
        error_count=int_or_none(row.get("error_count")),
    )


def _duration_ms(started_at: datetime, ended_at: datetime | None) -> float | None:
    if ended_at is None:
        return None
    return (ended_at - started_at).total_seconds() * 1000


def _none_if_zero_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if value == _ZERO_DATETIME or value.timestamp() == 0:
        return None
    return value


def _string_list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    values = [str(item) for item in value if str(item)]
    return values
