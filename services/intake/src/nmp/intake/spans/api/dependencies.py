# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared dependencies for Intake trace endpoints."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from nemo_platform import AsyncNeMoPlatform
from nmp.common.service.dependencies import get_sdk_client
from nmp.intake.spans.annotations_repository import AnnotationsRepository
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient, get_clickhouse_client
from nmp.intake.spans.evaluator_results_repository import EvaluatorResultsRepository
from nmp.intake.spans.service import IntakeSpansService
from nmp.intake.spans.session_repository import SessionRepository
from nmp.intake.spans.span_repository import SpanRepository
from nmp.intake.spans.trace_repository import TraceRepository


async def require_workspace_access(
    workspace: str,
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> None:
    """Validate that the request principal can access the path workspace."""

    await sdk.workspaces.retrieve(workspace)


def validate_list_query_params(request: Request, additional_params: set[str] | None = None) -> None:
    """Reject unsupported top-level query params while allowing deep-object filters."""

    allowed = {"page", "page_size", "sort", "filter"}
    if additional_params is not None:
        allowed.update(additional_params)

    unsupported = []
    for key in request.query_params.keys():
        if key in allowed or key.startswith("filter["):
            continue
        unsupported.append(key)

    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported query parameter(s): {', '.join(sorted(set(unsupported)))}",
        )


def get_span_repository(
    client: Annotated[ClickHouseSpanClient, Depends(get_clickhouse_client)],
) -> SpanRepository:
    return SpanRepository(client)


def get_trace_repository(
    client: Annotated[ClickHouseSpanClient, Depends(get_clickhouse_client)],
) -> TraceRepository:
    return TraceRepository(client)


def get_session_repository(
    client: Annotated[ClickHouseSpanClient, Depends(get_clickhouse_client)],
) -> SessionRepository:
    return SessionRepository(client)


def get_evaluator_results_repository(
    client: Annotated[ClickHouseSpanClient, Depends(get_clickhouse_client)],
) -> EvaluatorResultsRepository:
    return EvaluatorResultsRepository(client)


def get_annotations_repository(
    client: Annotated[ClickHouseSpanClient, Depends(get_clickhouse_client)],
) -> AnnotationsRepository:
    return AnnotationsRepository(client)


def get_spans_service(
    span_repository: Annotated[SpanRepository, Depends(get_span_repository)],
    trace_repository: Annotated[TraceRepository, Depends(get_trace_repository)],
    session_repository: Annotated[SessionRepository, Depends(get_session_repository)],
    evaluator_results_repository: Annotated[EvaluatorResultsRepository, Depends(get_evaluator_results_repository)],
    annotations_repository: Annotated[AnnotationsRepository, Depends(get_annotations_repository)],
) -> IntakeSpansService:
    return IntakeSpansService(
        span_repository,
        trace_repository,
        session_repository,
        evaluator_results_repository,
        annotations_repository,
    )


SpansServiceDep = Annotated[IntakeSpansService, Depends(get_spans_service)]
