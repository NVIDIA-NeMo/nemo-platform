# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI routes for InsightTrace CRUD.

InsightTrace is a join entity. Its name is composed from (insight, trace_id) so
the underlying per-name uniqueness of the entity store enforces the join
constraint. Callers POST with ``insight`` and ``trace_id``; the server composes
the name.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_insights_plugin.entities import InsightTrace, compose_insight_trace_name
from nemo_insights_plugin.schema import (
    CreateInsightTraceRequest,
    InsightTraceFilter,
    InsightTracePage,
    UpdateInsightTraceRequest,
)
from nemo_platform_plugin.entity_client import (
    NemoEntitiesClient,
    NemoEntityConflictError,
    NemoEntityNotFoundError,
    get_entity_client,
)
from nemo_platform_plugin.schema import PaginationData
from nmp.common.entities.filters import make_filter_obj_dep

logger = logging.getLogger(__name__)


def build_insight_traces_router() -> APIRouter:
    router = APIRouter()
    _filter_dep = make_filter_obj_dep(InsightTraceFilter)

    @router.post(
        "/insight_traces",
        response_model=InsightTrace,
        status_code=201,
        tags=["Insights · Insight Traces"],
    )
    async def create_insight_trace(
        workspace: str,
        body: CreateInsightTraceRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> InsightTrace:
        name = compose_insight_trace_name(body.insight, body.trace_id)
        link = InsightTrace(
            name=name,
            workspace=workspace,
            insight=body.insight,
            trace_id=body.trace_id,
            role=body.role,
            note=body.note,
        )
        try:
            return await entity_client.create(link)
        except NemoEntityConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Trace '{body.trace_id}' is already attached to insight '{body.insight}' "
                    f"in workspace '{workspace}'."
                ),
            ) from exc
        except Exception as exc:
            logger.exception("Failed to create insight_trace '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to create insight_trace.") from exc

    @router.get(
        "/insight_traces",
        response_model=InsightTracePage,
        tags=["Insights · Insight Traces"],
    )
    async def list_insight_traces(
        workspace: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        sort: str = Query(default="-created_at"),
        filter: InsightTraceFilter = Depends(_filter_dep),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> InsightTracePage:
        filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
        try:
            result = await entity_client.list(
                InsightTrace,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
                filter_obj=filter_dict or None,
            )
        except Exception as exc:
            logger.exception("Failed to list insight_traces in workspace '%s'", workspace)
            raise HTTPException(status_code=500, detail="Failed to list insight_traces.") from exc

        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return InsightTracePage(data=result.data, pagination=pagination, sort=sort, filter=filter)

    @router.get(
        "/insight_traces/{name}",
        response_model=InsightTrace,
        tags=["Insights · Insight Traces"],
    )
    async def get_insight_trace(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> InsightTrace:
        try:
            return await entity_client.get(InsightTrace, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"InsightTrace '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to get insight_trace '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to get insight_trace.") from exc

    @router.patch(
        "/insight_traces/{name}",
        response_model=InsightTrace,
        tags=["Insights · Insight Traces"],
    )
    async def update_insight_trace(
        workspace: str,
        name: str,
        body: UpdateInsightTraceRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> InsightTrace:
        try:
            link = await entity_client.get(InsightTrace, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"InsightTrace '{name}' not found in workspace '{workspace}'.",
            ) from exc

        if body.role is not None:
            link.role = body.role
        if body.note is not None:
            link.note = body.note

        try:
            return await entity_client.update(link)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"InsightTrace '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to update insight_trace '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to update insight_trace.") from exc

    @router.delete(
        "/insight_traces/{name}",
        status_code=204,
        tags=["Insights · Insight Traces"],
    )
    async def delete_insight_trace(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> None:
        try:
            await entity_client.delete(InsightTrace, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"InsightTrace '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to delete insight_trace '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to delete insight_trace.") from exc

    return router
