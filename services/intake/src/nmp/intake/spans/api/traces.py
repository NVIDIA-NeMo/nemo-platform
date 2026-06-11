# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read API for ClickHouse-backed Intake trace summaries."""

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
from nmp.intake.spans.api.traces_schemas import Trace, TraceFilter, TraceMode, TraceSortField
from nmp.intake.spans.domain import SpanStatus, TraceListFilter
from nmp.intake.spans.service import TraceNotFoundError
from nmp.intake.spans.storage import utc_now

router = APIRouter(dependencies=[Depends(require_workspace_access)])
API_TAG = "Traces"
DEFAULT_LIST_LOOKBACK_DAYS = 30
TRACE_INDEX_FILTER_FIELDS = frozenset(
    {
        "experiment_id",
        "test_case_id",
    }
)
TRACE_INDEX_FILTER_ALIASES = {
    "experiment_id": "experiment_id",
    "test_case_id": "test_case_id",
}


@router.get(
    "/v2/workspaces/{workspace}/traces",
    response_model=Page[Trace],
    response_model_exclude_none=True,
    tags=[API_TAG],
    openapi_extra=generate_openapi_extra_params(
        filter_schema=TraceFilter,
        filter_description=(
            "Filter root-span-backed traces by id, session_id, root status, root span started_at, "
            "experiment_id, and test_case_id."
        ),
    ),
)
async def list_traces(
    workspace: str,
    request: Request,
    service: SpansServiceDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=10, ge=1, le=1000, description="Page size."),
    sort: TraceSortField = Query(default=TraceSortField.STARTED_AT_DESC),
    mode: TraceMode = Query(
        default="detailed",
        description="Use summary for root-span trace fields only, or detailed to include token, cost, and span-count rollups.",
    ),
    parsed: ParsedFilter = Depends(make_filter_dep(TraceFilter)),
) -> Page[Trace]:
    validate_list_query_params(request, additional_params={"mode"})
    filters = _trace_filter(workspace, parsed)
    _apply_default_time_bound(filters)
    result = await service.list_traces(
        filters=filters,
        page=page,
        page_size=page_size,
        sort=sort.value,
        mode=mode,
    )
    traces = [Trace.from_domain(trace) for trace in result.data]
    return Page[Trace](
        data=traces,
        pagination=result.pagination,
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/traces/{id}",
    response_model=Trace,
    response_model_exclude_none=True,
    tags=[API_TAG],
)
async def get_trace(
    workspace: str,
    id: str,
    service: SpansServiceDep,
    mode: TraceMode = Query(
        default="detailed",
        description="Use summary for root-span trace fields only, or detailed to include token, cost, and span-count rollups.",
    ),
) -> Trace:
    try:
        trace = await service.get_trace(workspace=workspace, trace_id=id, mode=mode)
    except TraceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trace {workspace}/{id} not found")
    return Trace.from_domain(trace)


def _trace_filter(workspace: str, parsed: ParsedFilter) -> TraceListFilter:
    filters = TraceListFilter(workspace=workspace)
    for comparison in filter_comparisons(parsed):
        if comparison.field == "id":
            filters.trace_id = require_string_value(comparison)
        elif comparison.field == "session_id":
            filters.session_id = require_string_value(comparison)
        elif comparison.field == "status":
            filters.status = require_enum_value(comparison, SpanStatus)
        elif comparison.field == "started_at" and comparison.operator == FilterOperator.GTE:
            filters.started_at_gte = require_datetime_value(comparison)
        elif comparison.field == "started_at" and comparison.operator == FilterOperator.LTE:
            filters.started_at_lte = require_datetime_value(comparison)
        elif comparison.field in TRACE_INDEX_FILTER_FIELDS:
            if comparison.operator != FilterOperator.EQ:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported trace filter: {comparison.field} {comparison.operator.value}",
                )
            _set_trace_index_filter(filters, comparison.field, require_string_value(comparison))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported trace filter: {comparison.field} {comparison.operator.value}",
            )
    return filters


def _set_trace_index_filter(filters: TraceListFilter, public_field: str, value: str) -> None:
    field = TRACE_INDEX_FILTER_ALIASES[public_field]
    current_value = getattr(filters, field)
    if current_value is not None and current_value != value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Conflicting trace filters for {field}",
        )
    setattr(filters, field, value)


def _apply_default_time_bound(filters: TraceListFilter) -> None:
    if filters.started_at_gte is None and filters.started_at_lte is None:
        filters.started_at_gte = utc_now() - timedelta(days=DEFAULT_LIST_LOOKBACK_DAYS)
