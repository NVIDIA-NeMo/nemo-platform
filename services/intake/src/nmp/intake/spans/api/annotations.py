# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""API for post-hoc annotations on spans and sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nmp.common.api.common import Page
from nmp.common.api.filter import FilterOperator
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.api.utils import generate_openapi_extra_params
from nmp.common.auth import AuthClient, get_auth_client
from nmp.intake.spans.api.annotations_schemas import (
    Annotation,
    AnnotationFilter,
    AnnotationInput,
    AnnotationSortField,
    AnnotationUpdate,
)
from nmp.intake.spans.api.dependencies import SpansServiceDep, require_workspace_access, validate_list_query_params
from nmp.intake.spans.api.query_filters import (
    filter_comparisons,
    require_datetime_value,
    require_enum_value,
    require_string_value,
)
from nmp.intake.spans.domain import Annotation as DomainAnnotation
from nmp.intake.spans.domain import AnnotationKind, AnnotationListFilter
from nmp.intake.spans.service import AnnotationNotFoundError
from pydantic import ValidationError

router = APIRouter(dependencies=[Depends(require_workspace_access)])
API_TAG = "Annotations"


@router.post(
    "/v2/workspaces/{workspace}/annotations",
    response_model=Annotation,
    response_model_exclude_none=True,
    tags=[API_TAG],
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation(
    workspace: str,
    body: AnnotationInput,
    service: SpansServiceDep,
    auth_client: AuthClient = Depends(get_auth_client),
) -> Annotation:
    now = datetime.now(timezone.utc)
    domain_annotation = DomainAnnotation(
        annotation_id=f"ann-{uuid4().hex}",
        workspace=workspace,
        span_id=body.span_id,
        session_id=body.session_id,
        kind=body.kind,
        name=body.name,
        value_text=body.value_text,
        value_numeric=body.value_numeric,
        text=body.text,
        metadata=body.metadata,
        created_by=_resolve_created_by(auth_client),
        created_at=now,
        ingested_at=now,
    )
    saved = await service.create_annotation(domain_annotation)
    return Annotation.from_domain(saved)


@router.get(
    "/v2/workspaces/{workspace}/annotations",
    response_model=Page[Annotation],
    response_model_exclude_none=True,
    tags=[API_TAG],
    openapi_extra=generate_openapi_extra_params(
        filter_schema=AnnotationFilter,
        filter_description=("Filter annotations by span_id, session_id, kind, name, created_by, and created_at range."),
    ),
)
async def list_annotations(
    workspace: str,
    request: Request,
    service: SpansServiceDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=10, ge=1, le=1000, description="Page size."),
    sort: AnnotationSortField = Query(default=AnnotationSortField.CREATED_AT_DESC),
    parsed: ParsedFilter = Depends(make_filter_dep(AnnotationFilter)),
) -> Page[Annotation]:
    validate_list_query_params(request)
    result = await service.list_annotations(
        filters=_annotation_filter(workspace, parsed),
        page=page,
        page_size=page_size,
        sort=sort.value,
    )
    rows = [Annotation.from_domain(item) for item in result.data]
    return Page[Annotation](
        data=rows,
        pagination=result.pagination,
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/annotations/{annotation_id}",
    response_model=Annotation,
    response_model_exclude_none=True,
    tags=[API_TAG],
)
async def get_annotation(
    workspace: str,
    annotation_id: str,
    service: SpansServiceDep,
) -> Annotation:
    try:
        annotation = await service.get_annotation(workspace=workspace, annotation_id=annotation_id)
    except AnnotationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Annotation {workspace}/{annotation_id} not found",
        ) from None
    return Annotation.from_domain(annotation)


@router.patch(
    "/v2/workspaces/{workspace}/annotations/{annotation_id}",
    response_model=Annotation,
    response_model_exclude_none=True,
    tags=[API_TAG],
)
async def update_annotation(
    workspace: str,
    annotation_id: str,
    body: AnnotationUpdate,
    service: SpansServiceDep,
) -> Annotation:
    try:
        existing = await service.get_annotation(workspace=workspace, annotation_id=annotation_id)
    except AnnotationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Annotation {workspace}/{annotation_id} not found",
        ) from None

    # Merge update onto existing, then re-validate against the kind.
    try:
        merged = _merge_update(existing, body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            # ``include_context=False`` strips ValueError objects that aren't JSON-serializable.
            detail=exc.errors(include_context=False),
        ) from None
    updated = await service.update_annotation(merged)
    return Annotation.from_domain(updated)


@router.delete(
    "/v2/workspaces/{workspace}/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[API_TAG],
)
async def delete_annotation(
    workspace: str,
    annotation_id: str,
    service: SpansServiceDep,
) -> None:
    try:
        await service.delete_annotation(workspace=workspace, annotation_id=annotation_id)
    except AnnotationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Annotation {workspace}/{annotation_id} not found",
        ) from None


@router.get(
    "/v2/workspaces/{workspace}/spans/{span_id}/annotations",
    response_model=list[Annotation],
    response_model_exclude_none=True,
    tags=[API_TAG],
)
async def list_annotations_for_span(
    workspace: str,
    span_id: str,
    service: SpansServiceDep,
) -> list[Annotation]:
    result = await service.list_annotations(
        filters=AnnotationListFilter(workspace=workspace, span_id=span_id),
        page=1,
        page_size=1000,
        sort=AnnotationSortField.CREATED_AT_ASC.value,
    )
    return [Annotation.from_domain(item) for item in result.data]


def _resolve_created_by(auth_client: AuthClient) -> str | None:
    if not getattr(auth_client, "auth_enabled", False):
        return None
    principal_id = getattr(getattr(auth_client, "principal", None), "id", None)
    return principal_id or None


def _annotation_filter(workspace: str, parsed: ParsedFilter) -> AnnotationListFilter:
    filters = AnnotationListFilter(workspace=workspace)
    for comparison in filter_comparisons(parsed):
        if comparison.field == "span_id":
            filters.span_id = require_string_value(comparison)
        elif comparison.field == "session_id":
            filters.session_id = require_string_value(comparison)
        elif comparison.field == "kind":
            filters.kind = require_enum_value(comparison, AnnotationKind)
        elif comparison.field == "name":
            filters.name = require_string_value(comparison)
        elif comparison.field == "created_by":
            filters.created_by = require_string_value(comparison)
        elif comparison.field == "created_at" and comparison.operator == FilterOperator.GTE:
            filters.created_at_gte = require_datetime_value(comparison)
        elif comparison.field == "created_at" and comparison.operator == FilterOperator.LTE:
            filters.created_at_lte = require_datetime_value(comparison)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported annotation filter: {comparison.field} {comparison.operator.value}",
            )
    return filters


def _merge_update(existing: DomainAnnotation, body: AnnotationUpdate) -> DomainAnnotation:
    """Apply a PATCH body to an existing annotation, preserving identity + kind.

    Only the value fields are updatable; kind, target, and authorship are immutable.
    The merged annotation is re-validated by AnnotationInput's kind-aware validator
    via a roundtrip through Pydantic so the patched row stays well-formed.
    """

    from nmp.intake.spans.api.annotations_schemas import _AnnotationFieldsMixin

    merged_name = body.name if body.name is not None else existing.name
    merged_value_text = body.value_text if body.value_text is not None else existing.value_text
    merged_value_numeric = body.value_numeric if body.value_numeric is not None else existing.value_numeric
    merged_text = body.text if body.text is not None else existing.text
    merged_metadata = body.metadata if body.metadata is not None else existing.metadata

    # Re-validate the merged result against the kind so PATCH can't produce an invalid row.
    _AnnotationFieldsMixin(
        kind=existing.kind,
        name=merged_name,
        value_text=merged_value_text,
        value_numeric=merged_value_numeric,
        text=merged_text,
        metadata=merged_metadata,
    )

    now = datetime.now(timezone.utc)
    return DomainAnnotation(
        annotation_id=existing.annotation_id,
        workspace=existing.workspace,
        span_id=existing.span_id,
        session_id=existing.session_id,
        kind=existing.kind,
        name=merged_name,
        value_text=merged_value_text,
        value_numeric=merged_value_numeric,
        text=merged_text,
        metadata=merged_metadata,
        created_by=existing.created_by,
        created_at=existing.created_at,
        ingested_at=now,
    )
