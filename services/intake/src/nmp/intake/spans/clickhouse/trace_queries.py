# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse trace rollup SQL for Intake."""

from __future__ import annotations

from typing import Any

from nmp.intake.spans.clickhouse._where import _as_clause, _new_where
from nmp.intake.spans.clickhouse.identifiers import column
from nmp.intake.spans.clickhouse.query import TableRef
from nmp.intake.spans.clickhouse.sql import BuiltQuery, _trusted_query, merge_parameters
from nmp.intake.spans.domain import TraceListFilter, TraceMode
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field

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

_ZERO_DATETIME_SQL = "toDateTime64(0, 6)"

METRIC_ATTRIBUTE_FIELDS = {
    "input_tokens": SpanAttributeField.INPUT_TOKENS,
    "output_tokens": SpanAttributeField.OUTPUT_TOKENS,
    "cached_tokens": SpanAttributeField.CACHED_TOKENS,
    "total_tokens": SpanAttributeField.TOTAL_TOKENS,
    "cost_usd": SpanAttributeField.COST_TOTAL_USD,
    "cost_input_usd": SpanAttributeField.COST_INPUT_USD,
    "cost_output_usd": SpanAttributeField.COST_OUTPUT_USD,
}


def _require_table_ref(table: TableRef) -> None:
    if not isinstance(table, TableRef):
        raise TypeError("trace query builders require a TableRef")


def trace_rows_sql(table: TableRef, filters: TraceListFilter, *, mode: TraceMode) -> BuiltQuery:
    _require_table_ref(table)
    summary_query = trace_summary_sql(table, filters)
    if mode == "detailed":
        rollup_query = trace_aggregates_sql(table, filters)
        include_aggregates = True
    elif mode == "summary":
        rollup_query = trace_status_sql(table, filters)
        include_aggregates = False
    else:
        raise ValueError(f"Unsupported trace mode: {mode}")

    sql = f"""
        SELECT
            {_trace_select_columns(include_aggregates=include_aggregates)}
        FROM ({summary_query.sql}) AS traces
        ANY INNER JOIN ({rollup_query.sql}) AS rollups
            ON traces.workspace = rollups.workspace
            AND traces.source_format = rollups.source_format
            AND traces.trace_id = rollups.trace_id
    """
    return _trusted_query(sql, merge_parameters(summary_query.parameters, rollup_query.parameters))


def trace_summary_sql(table: TableRef, filters: TraceListFilter) -> BuiltQuery:
    root_alias = "root_spans"
    current_spans = current_spans_sql(table)
    where_sql, parameters = _trace_summary_where(table, filters, qualifier=root_alias).build()
    sql = f"""
        SELECT
            {root_alias}.trace_id AS trace_id,
            {root_alias}.trace_id AS id,
            {root_alias}.workspace AS workspace,
            {root_alias}.session_id AS session_id,
            {root_alias}.source_format AS source_format,
            nullIf({root_alias}.external_span_id, '') AS root_span_id,
            nullIf({root_alias}.name, '') AS name,
            nullIf({root_alias}.input, '') AS input,
            nullIf({root_alias}.output, '') AS output,
            {root_alias}.start_time AS started_at,
            nullIf({root_alias}.end_time, {_ZERO_DATETIME_SQL}) AS ended_at,
            {root_alias}.attributes_string AS root_attributes_string,
            {root_alias}.event_ts AS ingested_at
        FROM {current_spans.sql} AS {root_alias}
        WHERE {where_sql}
        ORDER BY {root_alias}.start_time ASC, {root_alias}.id ASC
        LIMIT 1 BY {root_alias}.workspace, {root_alias}.source_format, {root_alias}.trace_id
    """
    return _trusted_query(sql, parameters)


def trace_status_sql(table: TableRef, filters: TraceListFilter) -> BuiltQuery:
    source_alias = "trace_spans"
    current_spans = current_spans_sql(table)
    where_sql, parameters = _trace_rollup_where(table, filters, qualifier=source_alias).build()
    sql = f"""
        SELECT
            {source_alias}.workspace AS workspace,
            {source_alias}.source_format AS source_format,
            {source_alias}.trace_id AS trace_id,
            {_rolled_up_status_sql(source_alias)} AS status
        FROM {current_spans.sql} AS {source_alias}
        WHERE {where_sql}
        GROUP BY {source_alias}.workspace, {source_alias}.source_format, {source_alias}.trace_id
    """
    return _trusted_query(sql, parameters)


def trace_aggregates_sql(table: TableRef, filters: TraceListFilter) -> BuiltQuery:
    source_alias = "trace_spans"
    current_spans = current_spans_sql(table)
    where_sql, parameters = _trace_rollup_where(table, filters, qualifier=source_alias).build()
    metric_columns, metric_parameters = _metric_columns(source_alias)
    parameters.update(metric_parameters)

    model_spec = spec_for_field(SpanAttributeField.MODEL)
    provider_spec = spec_for_field(SpanAttributeField.PROVIDER)
    parameters["model_key"] = model_spec.bag_key
    parameters["provider_key"] = provider_spec.bag_key

    sql = f"""
        SELECT
            {source_alias}.workspace AS workspace,
            {source_alias}.source_format AS source_format,
            {source_alias}.trace_id AS trace_id,
            {_rolled_up_status_sql(source_alias)} AS status,
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
        FROM {current_spans.sql} AS {source_alias}
        WHERE {where_sql}
        GROUP BY {source_alias}.workspace, {source_alias}.source_format, {source_alias}.trace_id
    """
    return _trusted_query(sql, parameters)


def current_spans_sql(table: TableRef) -> BuiltQuery:
    _require_table_ref(table)
    source_alias = "span_versions"
    columns = [
        *[f"{source_alias}.{column_name} AS {column_name}" for column_name in _CURRENT_SPAN_IDENTITY_COLUMNS],
        *[
            f"argMax({source_alias}.{column_name}, ({source_alias}.event_ts, {source_alias}.is_deleted)) AS {column_name}"
            for column_name in _CURRENT_SPAN_VALUE_COLUMNS
        ],
    ]
    columns_sql = ",\n                ".join(columns)
    group_by_sql = ", ".join(f"{source_alias}.{column_name}" for column_name in _CURRENT_SPAN_IDENTITY_COLUMNS)
    return _trusted_query(f"""
        (
            SELECT
                {columns_sql}
            FROM {table.qualified_name} AS {source_alias}
            WHERE {source_alias}.workspace = %(workspace)s
            GROUP BY {group_by_sql}
        )
    """)


def _trace_summary_where(table: TableRef, filters: TraceListFilter, *, qualifier: str):
    where = _trace_identity_where(table, filters, qualifier=qualifier)
    where.is_empty_parent_span(qualifier=qualifier)
    if filters.started_at_gte is not None:
        where.gte(column("start_time", qualifier=qualifier), "started_at_gte", filters.started_at_gte)
    if filters.started_at_lte is not None:
        where.lte(column("start_time", qualifier=qualifier), "started_at_lte", filters.started_at_lte)
    return _as_clause(where)


def _trace_rollup_where(table: TableRef, filters: TraceListFilter, *, qualifier: str):
    return _as_clause(_trace_identity_where(table, filters, qualifier=qualifier))


def _trace_identity_where(
    table: TableRef,
    filters: TraceListFilter,
    *,
    qualifier: str,
):
    where = (
        _new_where()
        .eq(column("workspace", qualifier=qualifier), "workspace", filters.workspace)
        .eq(column("is_deleted", qualifier=qualifier), "is_deleted", 0)
    )

    if filters.trace_id is not None:
        where.eq(column("trace_id", qualifier=qualifier), "trace_id", filters.trace_id)
    if filters.session_id is not None:
        where.eq(column("session_id", qualifier=qualifier), "session_id", filters.session_id)
    if filters.source_format is not None:
        where.eq(column("source_format", qualifier=qualifier), "source_format", filters.source_format)

    root_query = _trace_candidate_subquery_sql(
        table=table,
        workspace=filters.workspace,
        attribute_filters=filters.root_attribute_filters,
        root_only=True,
        prefix="root_candidate",
    )
    if root_query:
        where.in_subquery(
            f"{column('workspace', qualifier=qualifier)}, "
            f"{column('source_format', qualifier=qualifier)}, "
            f"{column('trace_id', qualifier=qualifier)}",
            root_query,
        )

    span_query = _trace_candidate_subquery_sql(
        table=table,
        workspace=filters.workspace,
        attribute_filters=filters.span_attribute_filters,
        root_only=False,
        prefix="span_candidate",
    )
    if span_query:
        where.in_subquery(
            f"{column('workspace', qualifier=qualifier)}, "
            f"{column('source_format', qualifier=qualifier)}, "
            f"{column('trace_id', qualifier=qualifier)}",
            span_query,
        )

    return where


def _trace_candidate_subquery_sql(
    *,
    table: TableRef,
    workspace: str,
    attribute_filters: list[Any],
    root_only: bool,
    prefix: str,
) -> BuiltQuery | None:
    if not attribute_filters:
        return None

    where = _new_where().eq(column("workspace"), "workspace", workspace).eq(column("is_deleted"), "is_deleted", 0)
    if root_only:
        where.is_empty_parent_span()
    for index, attribute_filter in enumerate(attribute_filters):
        where.attribute_predicate(
            attribute_filter.field,
            attribute_filter.operator,
            attribute_filter.value,
            param_prefix=f"{prefix}_{index}",
        )

    where_sql, parameters = where.build()
    current_spans = current_spans_sql(table)
    return _trusted_query(
        f"""
        SELECT workspace, source_format, trace_id
        FROM {current_spans.sql} AS candidate_spans
        WHERE {where_sql}
        """,
        parameters,
    )


def _trace_select_columns(*, include_aggregates: bool) -> str:
    aggregate_columns = [
        f"rollups.{metric_column} AS {metric_column}" if include_aggregates else f"NULL AS {metric_column}"
        for metric_column in (
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
        "traces.started_at AS started_at",
        "traces.ended_at AS ended_at",
        "rollups.status AS status",
        *aggregate_columns,
        "traces.root_attributes_string AS root_attributes_string",
        "traces.ingested_at AS ingested_at",
    ]
    return ",\n            ".join(columns)


def _rolled_up_status_sql(source_alias: str) -> str:
    return f"""
            multiIf(
                countIf({source_alias}.status = 'error') > 0, 'error',
                countIf({source_alias}.status = 'cancelled') > 0, 'cancelled',
                countIf({source_alias}.status = 'unknown') = count(), 'unknown',
                'success'
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
