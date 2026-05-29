# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted ClickHouse WHERE clause builders for Intake span repositories."""

from __future__ import annotations

from nmp.intake.spans.clickhouse._where import WhereClause, _as_clause, _new_where
from nmp.intake.spans.clickhouse.identifiers import column
from nmp.intake.spans.domain import (
    AnnotationListFilter,
    EvaluatorResultListFilter,
    SpanListFilter,
    TraceListFilter,
)


def span_list_where(filters: SpanListFilter) -> WhereClause:
    where = (
        _new_where().eq(column("workspace"), "workspace", filters.workspace).eq(column("is_deleted"), "is_deleted", 0)
    )
    if filters.session_id is not None:
        where.eq(column("session_id"), "session_id", filters.session_id)
    if filters.trace_id is not None:
        where.eq(column("trace_id"), "trace_id", filters.trace_id)
    if filters.external_parent_span_id is not None:
        where.eq(column("external_parent_span_id"), "external_parent_span_id", filters.external_parent_span_id)
    if filters.source_format is not None:
        where.eq(column("source_format"), "source_format", filters.source_format)
    if filters.kind is not None:
        where.eq(column("kind"), "kind", filters.kind.value)
    if filters.status is not None:
        where.eq(column("status"), "status", filters.status.value)
    if filters.started_at_gte is not None:
        where.gte(column("start_time"), "started_at_gte", filters.started_at_gte)
    if filters.started_at_lte is not None:
        where.lte(column("start_time"), "started_at_lte", filters.started_at_lte)
    for index, attribute_filter in enumerate(filters.attribute_filters):
        where.attribute_predicate(
            attribute_filter.field,
            attribute_filter.operator,
            attribute_filter.value,
            param_prefix=f"attr_{index}",
        )
    return _as_clause(where)


def span_lookup_where(*, workspace: str, span_id: str) -> WhereClause:
    where = (
        _new_where()
        .eq(column("workspace"), "workspace", workspace)
        .eq(column("external_span_id"), "span_id", span_id)
        .eq(column("is_deleted"), "is_deleted", 0)
    )
    return _as_clause(where)


def annotation_list_where(filters: AnnotationListFilter) -> WhereClause:
    where = (
        _new_where().eq(column("workspace"), "workspace", filters.workspace).eq(column("is_deleted"), "is_deleted", 0)
    )
    if filters.span_id is not None:
        where.eq(column("span_id"), "span_id", filters.span_id)
    if filters.session_id is not None:
        where.eq(column("session_id"), "session_id", filters.session_id)
    if filters.kind is not None:
        where.eq(column("kind"), "kind", filters.kind.value)
    if filters.name is not None:
        where.eq(column("name"), "name", filters.name)
    if filters.value_text is not None:
        where.eq(column("value_text"), "value_text", filters.value_text)
    if filters.value_numeric_gte is not None:
        where.gte(column("value_numeric"), "value_numeric_gte", filters.value_numeric_gte)
    if filters.value_numeric_lte is not None:
        where.lte(column("value_numeric"), "value_numeric_lte", filters.value_numeric_lte)
    if filters.created_by is not None:
        where.eq(column("created_by"), "created_by", filters.created_by)
    if filters.created_at_gte is not None:
        where.gte(column("created_at"), "created_at_gte", filters.created_at_gte)
    if filters.created_at_lte is not None:
        where.lte(column("created_at"), "created_at_lte", filters.created_at_lte)
    return _as_clause(where)


def annotation_lookup_where(*, workspace: str, annotation_id: str) -> WhereClause:
    where = (
        _new_where()
        .eq(column("workspace"), "workspace", workspace)
        .eq(column("annotation_id"), "annotation_id", annotation_id)
        .eq(column("is_deleted"), "is_deleted", 0)
    )
    return _as_clause(where)


def evaluator_result_list_where(filters: EvaluatorResultListFilter) -> WhereClause:
    where = _new_where().eq(column("workspace"), "workspace", filters.workspace)
    if filters.span_id is not None:
        where.eq(column("span_id"), "span_id", filters.span_id)
    if filters.session_id is not None:
        where.eq(column("session_id"), "session_id", filters.session_id)
    if filters.name is not None:
        where.eq(column("name"), "name", filters.name)
    if filters.data_type is not None:
        where.eq(column("data_type"), "data_type", filters.data_type.value)
    if filters.created_by is not None:
        where.eq(column("created_by"), "created_by", filters.created_by)
    if filters.value_gte is not None:
        where.gte(column("value"), "value_gte", filters.value_gte)
    if filters.value_lte is not None:
        where.lte(column("value"), "value_lte", filters.value_lte)
    if filters.created_at_gte is not None:
        where.gte(column("created_at"), "created_at_gte", filters.created_at_gte)
    if filters.created_at_lte is not None:
        where.lte(column("created_at"), "created_at_lte", filters.created_at_lte)
    return _as_clause(where)


def evaluator_result_lookup_where(*, workspace: str, evaluator_result_id: str) -> WhereClause:
    where = (
        _new_where()
        .eq(column("workspace"), "workspace", workspace)
        .eq(column("evaluator_result_id"), "evaluator_result_id", evaluator_result_id)
    )
    return _as_clause(where)


def evaluator_results_for_span_where(*, workspace: str, span_id: str) -> WhereClause:
    where = _new_where().eq(column("workspace"), "workspace", workspace).eq(column("span_id"), "span_id", span_id)
    return _as_clause(where)


def trace_outer_where(filters: TraceListFilter) -> WhereClause:
    where = _new_where()
    if filters.status is not None:
        where.eq("status", "status", filters.status.value)
    return _as_clause(where)
