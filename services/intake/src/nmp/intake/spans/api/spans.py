# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read API for ClickHouse-backed Intake spans."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nmp.common.api.common import Page
from nmp.common.api.filter import FilterOperator
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.api.utils import generate_openapi_extra_params
from nmp.intake.spans.api.dependencies import SpansServiceDep, require_workspace_access, validate_list_query_params
from nmp.intake.spans.api.query_filters import (
    filter_comparisons,
    require_datetime_value,
    require_enum_value,
    require_string_value,
)
from nmp.intake.spans.api.spans_schemas import (
    Span,
    SpanFilter,
    SpanGroup,
    SpanGroupBy,
    SpanGroupSortField,
    SpanGroupsPage,
    SpanKind,
    SpanMode,
    SpanSortField,
    SpanStatus,
)
from nmp.intake.spans.domain import SpanAttributeFilter, SpanListFilter
from nmp.intake.spans.service import SpanNotFoundError
from nmp.intake.spans.storage import utc_now

router = APIRouter(dependencies=[Depends(require_workspace_access)])
API_TAG = "Spans"
DEFAULT_LIST_LOOKBACK_DAYS = 30
ATTRIBUTE_EQ_FILTER_FIELDS = frozenset(
    {
        "project",
        "evaluation_id",
        "evaluation_sha",
        "evaluation_run_id",
        "dataset_id",
        "dataset_name",
        "dataset_version",
        "test_case_id",
        "model",
        "tool_name",
        "provider",
        "agent_id",
        "agent_name",
        "prompt_name",
        "prompt_version",
    }
)


@router.get(
    "/v2/workspaces/{workspace}/spans",
    response_model=Page[Span],
    response_model_exclude_none=True,
    tags=[API_TAG],
    openapi_extra=generate_openapi_extra_params(
        filter_schema=SpanFilter,
        filter_description=(
            "Filter spans by session_id, trace_id, parent_span_id, project, evaluation context fields, "
            "source, kind, status, model, tool_name, provider, agent_id, agent_name, "
            "prompt_name, prompt_version, and started_at."
        ),
    ),
)
async def list_spans(
    workspace: str,
    request: Request,
    service: SpansServiceDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=10, ge=1, le=1000, description="Page size."),
    sort: SpanSortField = Query(default=SpanSortField.STARTED_AT_DESC),
    mode: SpanMode = Query(default="detailed"),
    parsed: ParsedFilter = Depends(make_filter_dep(SpanFilter)),
) -> Page[Span]:
    validate_list_query_params(request, additional_params={"mode"})
    filters = _span_filter(workspace, parsed)
    _apply_default_time_bound(filters)
    result = await service.list_spans(
        filters=filters,
        page=page,
        page_size=page_size,
        sort=sort.value,
    )
    spans = [Span.from_domain(span, mode=mode) for span in result.data]
    return Page[Span](
        data=spans,
        pagination=result.pagination,
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/spans/groups",
    response_model=SpanGroupsPage,
    response_model_exclude_none=True,
    tags=[API_TAG],
    responses={
        400: {
            "description": "Invalid group-by parameter",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"detail": {"type": "string"}},
                        "required": ["detail"],
                    }
                }
            },
        }
    },
    openapi_extra=generate_openapi_extra_params(
        filter_schema=SpanFilter,
        filter_description=(
            "Filter spans by the same fields as the span list endpoint, then group matching spans by the "
            "comma-separated fields in the by query parameter."
        ),
    ),
)
async def list_span_groups(
    workspace: str,
    request: Request,
    service: SpansServiceDep,
    by: str = Query(description="Comma-separated span fields to group by, e.g. trace_id or session_id,trace_id."),
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=10, ge=1, le=1000, description="Page size."),
    sort: SpanGroupSortField = Query(default=SpanGroupSortField.SPAN_COUNT_DESC),
    parsed: ParsedFilter = Depends(make_filter_dep(SpanFilter)),
) -> SpanGroupsPage:
    validate_list_query_params(request, additional_params={"by"})
    grouped_by = _parse_group_by(by)
    filters = _span_filter(workspace, parsed)
    _apply_default_time_bound(filters)
    result = await service.list_span_groups(
        filters=filters,
        group_by=[field.value for field in grouped_by],
        page=page,
        page_size=page_size,
        sort=sort.value,
    )
    groups = [SpanGroup.from_domain(group) for group in result.data]
    return SpanGroupsPage(
        grouped_by=grouped_by,
        data=groups,
        pagination=result.pagination,
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/spans/{span_id}",
    response_model=Span,
    response_model_exclude_none=True,
    tags=[API_TAG],
)
async def get_span(
    workspace: str,
    span_id: str,
    service: SpansServiceDep,
) -> Span:
    try:
        span = await service.get_span(workspace=workspace, span_id=span_id)
    except SpanNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Span {workspace}/{span_id} not found")
    return Span.from_domain(span)


def _parse_group_by(value: str) -> list[SpanGroupBy]:
    raw_fields = [field.strip() for field in value.split(",") if field.strip()]
    if not raw_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one group-by field is required.")

    grouped_by: list[SpanGroupBy] = []
    seen: set[SpanGroupBy] = set()
    for raw_field in raw_fields:
        try:
            field = SpanGroupBy(raw_field)
        except ValueError:
            allowed = ", ".join(item.value for item in SpanGroupBy)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported span group-by field: {raw_field}. Allowed fields: {allowed}",
            ) from None
        if field in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate span group-by field: {field.value}",
            )
        grouped_by.append(field)
        seen.add(field)
    return grouped_by


def _span_filter(workspace: str, parsed: ParsedFilter) -> SpanListFilter:
    filters = SpanListFilter(workspace=workspace)
    for comparison in filter_comparisons(parsed):
        if comparison.field == "session_id":
            filters.session_id = require_string_value(comparison)
        elif comparison.field == "trace_id":
            filters.trace_id = require_string_value(comparison)
        elif comparison.field == "parent_span_id":
            filters.external_parent_span_id = require_string_value(comparison)
        elif comparison.field in ATTRIBUTE_EQ_FILTER_FIELDS:
            _add_attribute_eq_filter(filters, comparison.field, require_string_value(comparison))
        elif comparison.field == "source":
            filters.source_format = require_string_value(comparison)
        elif comparison.field == "kind":
            filters.kind = require_enum_value(comparison, SpanKind)
        elif comparison.field == "status":
            filters.status = require_enum_value(comparison, SpanStatus)
        elif comparison.field == "started_at" and comparison.operator == FilterOperator.GTE:
            filters.started_at_gte = require_datetime_value(comparison)
        elif comparison.field == "started_at" and comparison.operator == FilterOperator.LTE:
            filters.started_at_lte = require_datetime_value(comparison)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported span filter: {comparison.field} {comparison.operator.value}",
            )
    return filters


def _add_attribute_eq_filter(filters: SpanListFilter, field: str, value: str) -> None:
    filters.attribute_filters.append(SpanAttributeFilter(field=field, operator=FilterOperator.EQ.value, value=value))


def _apply_default_time_bound(filters: SpanListFilter) -> None:
    if filters.started_at_gte is None and filters.started_at_lte is None:
        filters.started_at_gte = utc_now() - timedelta(days=DEFAULT_LIST_LOOKBACK_DAYS)
