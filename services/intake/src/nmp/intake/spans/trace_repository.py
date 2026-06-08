# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake trace reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import IntakeTrace, TraceEvaluationContext, TraceListFilter, TraceMode
from nmp.intake.spans.span_attribute_bags import SpanAttributeBags
from nmp.intake.spans.span_attribute_catalog import COST_SCALE, SpanAttributeField, spec_for_field, where_clause
from nmp.intake.spans.span_semantic_attributes import SpanSemanticAttributes
from nmp.intake.spans.storage import make_pagination, normalize_span_status, result_rows

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
    "started_at",
    "ended_at",
    "status",
    *METRIC_ATTRIBUTE_FIELDS.keys(),
    "models",
    "providers",
    "span_count",
    "error_count",
    "root_attributes_string",
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
_ZERO_DATETIME_SQL = "toDateTime64(0, 6)"


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
        trace_sql, parameters = _trace_rows_sql(self._client.table("spans"), filters, mode=mode)
        outer_where_sql, outer_parameters = _trace_outer_where(filters)
        all_parameters = {**parameters, **outer_parameters}

        total_result = await self._client.query(
            f"""
            SELECT count()
            FROM ({trace_sql}) AS traces
            WHERE {outer_where_sql}
            """,
            parameters=all_parameters,
        )
        total_results = int(total_result.result_rows[0][0])

        offset = (page - 1) * page_size
        rows_result = await self._client.query(
            f"""
            SELECT *
            FROM ({trace_sql}) AS traces
            WHERE {outer_where_sql}
            ORDER BY {_order_by(sort)}
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            parameters={**all_parameters, "limit": page_size, "offset": offset},
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


def _trace_rows_sql(table: str, filters: TraceListFilter, *, mode: TraceMode) -> tuple[str, dict[str, Any]]:
    summary_sql, summary_parameters = _trace_summary_sql(table, filters)
    if mode == "detailed":
        rollup_sql, rollup_parameters = _trace_aggregates_sql(table, filters)
        include_aggregates = True
    elif mode == "summary":
        rollup_sql, rollup_parameters = _trace_status_sql(table, filters)
        include_aggregates = False
    else:
        raise ValueError(f"Unsupported trace mode: {mode}")

    query = f"""
        SELECT
            {_trace_select_columns(include_aggregates=include_aggregates)}
        FROM ({summary_sql}) AS traces
        ANY INNER JOIN ({rollup_sql}) AS rollups
            ON traces.workspace = rollups.workspace
            AND traces.source_format = rollups.source_format
            AND traces.trace_id = rollups.trace_id
    """
    return query, {**summary_parameters, **rollup_parameters}


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
        "traces.started_at AS started_at",
        "traces.ended_at AS ended_at",
        "rollups.status AS status",
        *aggregate_columns,
        "traces.root_attributes_string AS root_attributes_string",
        "traces.ingested_at AS ingested_at",
    ]
    return ",\n            ".join(columns)


def _trace_summary_sql(table: str, filters: TraceListFilter) -> tuple[str, dict[str, Any]]:
    root_alias = "root_spans"
    base_where_sql, parameters = _trace_summary_where(table, filters, qualifier=root_alias)
    query = f"""
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
        FROM {current_spans_sql(table)} AS {root_alias}
        WHERE {base_where_sql}
        ORDER BY {root_alias}.start_time ASC, {root_alias}.id ASC
        LIMIT 1 BY {root_alias}.workspace, {root_alias}.source_format, {root_alias}.trace_id
    """
    return query, parameters


def _trace_status_sql(table: str, filters: TraceListFilter) -> tuple[str, dict[str, Any]]:
    source_alias = "trace_spans"
    base_where_sql, parameters = _trace_rollup_where(table, filters, qualifier=source_alias)
    query = f"""
        SELECT
            {source_alias}.workspace AS workspace,
            {source_alias}.source_format AS source_format,
            {source_alias}.trace_id AS trace_id,
            {_rolled_up_status_sql(source_alias)} AS status
        FROM {current_spans_sql(table)} AS {source_alias}
        WHERE {base_where_sql}
        GROUP BY {source_alias}.workspace, {source_alias}.source_format, {source_alias}.trace_id
    """
    return query, parameters


def _trace_aggregates_sql(table: str, filters: TraceListFilter) -> tuple[str, dict[str, Any]]:
    source_alias = "trace_spans"
    base_where_sql, parameters = _trace_rollup_where(table, filters, qualifier=source_alias)
    metric_columns, metric_parameters = _metric_columns(source_alias)
    parameters.update(metric_parameters)

    model_spec = spec_for_field(SpanAttributeField.MODEL)
    provider_spec = spec_for_field(SpanAttributeField.PROVIDER)
    parameters["model_key"] = model_spec.bag_key
    parameters["provider_key"] = provider_spec.bag_key

    query = f"""
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
        FROM {current_spans_sql(table)} AS {source_alias}
        WHERE {base_where_sql}
        GROUP BY {source_alias}.workspace, {source_alias}.source_format, {source_alias}.trace_id
    """
    return query, parameters


def _rolled_up_status_sql(source_alias: str) -> str:
    return f"""
            multiIf(
                countIf({source_alias}.status = 'error') > 0, 'error',
                countIf({source_alias}.status = 'cancelled') > 0, 'cancelled',
                countIf({source_alias}.status = 'unknown') = count(), 'unknown',
                'success'
            )
        """


def _trace_summary_where(table: str, filters: TraceListFilter, *, qualifier: str) -> tuple[str, dict[str, Any]]:
    clauses, parameters = _trace_identity_where(table, filters, qualifier=qualifier)

    def column(name: str) -> str:
        return f"{qualifier}.{name}"

    clauses.append(f"{column('external_parent_span_id')} = ''")
    if filters.started_at_gte is not None:
        clauses.append(f"{column('start_time')} >= %(started_at_gte)s")
        parameters["started_at_gte"] = filters.started_at_gte
    if filters.started_at_lte is not None:
        clauses.append(f"{column('start_time')} <= %(started_at_lte)s")
        parameters["started_at_lte"] = filters.started_at_lte

    return " AND ".join(clauses), parameters


def _trace_rollup_where(table: str, filters: TraceListFilter, *, qualifier: str) -> tuple[str, dict[str, Any]]:
    clauses, parameters = _trace_identity_where(table, filters, qualifier=qualifier)
    return " AND ".join(clauses), parameters


def _trace_identity_where(
    table: str,
    filters: TraceListFilter,
    *,
    qualifier: str,
) -> tuple[list[str], dict[str, Any]]:
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

    root_sql, root_parameters = _candidate_subquery(
        table=table,
        workspace=filters.workspace,
        attribute_filters=filters.root_attribute_filters,
        root_only=True,
        prefix="root_candidate",
    )
    if root_sql:
        clauses.append(f"({column('workspace')}, {column('source_format')}, {column('trace_id')}) IN ({root_sql})")
        parameters.update(root_parameters)

    span_sql, span_parameters = _candidate_subquery(
        table=table,
        workspace=filters.workspace,
        attribute_filters=filters.span_attribute_filters,
        root_only=False,
        prefix="span_candidate",
    )
    if span_sql:
        clauses.append(f"({column('workspace')}, {column('source_format')}, {column('trace_id')}) IN ({span_sql})")
        parameters.update(span_parameters)

    return clauses, parameters


def _candidate_subquery(
    *,
    table: str,
    workspace: str,
    attribute_filters: list[Any],
    root_only: bool,
    prefix: str,
) -> tuple[str | None, dict[str, Any]]:
    if not attribute_filters:
        return None, {}

    clauses = ["workspace = %(workspace)s", "is_deleted = 0"]
    if root_only:
        clauses.append("external_parent_span_id = ''")

    parameters: dict[str, Any] = {"workspace": workspace}
    for index, attribute_filter in enumerate(attribute_filters):
        clause, clause_parameters = where_clause(
            attribute_filter.field,
            attribute_filter.operator,
            attribute_filter.value,
            param_prefix=f"{prefix}_{index}",
        )
        clauses.append(f"({clause})")
        parameters.update(clause_parameters)

    return (
        f"""
        SELECT workspace, source_format, trace_id
        FROM {current_spans_sql(table)} AS candidate_spans
        WHERE {" AND ".join(clauses)}
        """,
        parameters,
    )


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


def _trace_outer_where(filters: TraceListFilter) -> tuple[str, dict[str, Any]]:
    clauses = ["1 = 1"]
    parameters: dict[str, Any] = {}

    if filters.status is not None:
        clauses.append("status = %(status)s")
        parameters["status"] = filters.status.value

    return " AND ".join(clauses), parameters


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


def _order_by(sort: str) -> str:
    direction = "DESC" if sort.startswith("-") else "ASC"
    field = sort.removeprefix("-")
    column = TRACE_SORT_COLUMNS.get(field)
    if column is None:
        raise ValueError(f"Unsupported trace sort field: {field}")
    return f"{column} {direction}, id ASC"


def _row_to_trace(row: dict[str, Any]) -> IntakeTrace:
    root_attributes = dict(row.get("root_attributes_string") or {})
    attribute_bags = SpanAttributeBags.from_domain_maps(
        attributes_string=root_attributes,
        attributes_number={},
        attributes_bool={},
    )
    semantic_attributes = SpanSemanticAttributes.from_bags(attribute_bags)
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
        project=semantic_attributes.project,
        evaluation_context=_evaluation_context(semantic_attributes, attribute_bags),
        started_at=row["started_at"],
        ended_at=ended_at,
        duration_ms=_duration_ms(row["started_at"], ended_at),
        ingested_at=row["ingested_at"],
        status=normalize_span_status(row.get("status")),
        input_tokens=_int_or_none(row.get("input_tokens")),
        output_tokens=_int_or_none(row.get("output_tokens")),
        cached_tokens=_int_or_none(row.get("cached_tokens")),
        total_tokens=_int_or_none(row.get("total_tokens")),
        cost_usd=_float_or_none(row.get("cost_usd")),
        cost_input_usd=_float_or_none(row.get("cost_input_usd")),
        cost_output_usd=_float_or_none(row.get("cost_output_usd")),
        models=_string_list_or_none(row.get("models")),
        providers=_string_list_or_none(row.get("providers")),
        span_count=_int_or_none(row.get("span_count")),
        error_count=_int_or_none(row.get("error_count")),
    )


def _evaluation_context(
    attributes: SpanSemanticAttributes,
    attribute_bags: SpanAttributeBags,
) -> TraceEvaluationContext | None:
    metadata = attribute_bags.evaluation_metadata()
    context = TraceEvaluationContext(
        evaluation_id=attributes.evaluation_id,
        evaluation_sha=attributes.evaluation_sha,
        evaluation_run_id=attributes.evaluation_run_id,
        dataset_id=attributes.dataset_id,
        dataset_name=attributes.dataset_name,
        dataset_version=attributes.dataset_version,
        test_case_id=attributes.test_case_id,
        metadata=metadata or {},
    )
    if metadata is None and not context.has_scalar_values():
        return None
    return context


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


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _string_list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    values = [str(item) for item in value if str(item)]
    return values
