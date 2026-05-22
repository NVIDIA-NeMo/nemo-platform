# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI routes for Insight CRUD.

Status-transition policy (enforced on PATCH):

* same-state writes are idempotent
* allowed transitions: ``open ↔ in_progress``, ``open|in_progress → resolved|deleted``,
  ``resolved → in_progress`` (reopening)
* everything else returns 400

DELETE sets ``status=deleted`` (soft delete) rather than removing the row, so the
audit trail of analyst findings is preserved.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_insights_plugin.entities import Insight, InsightStatus
from nemo_insights_plugin.schema import (
    CreateInsightRequest,
    InsightFilter,
    InsightPage,
    UpdateInsightRequest,
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


_ALLOWED_TRANSITIONS: dict[InsightStatus, set[InsightStatus]] = {
    InsightStatus.OPEN: {InsightStatus.OPEN, InsightStatus.IN_PROGRESS, InsightStatus.RESOLVED, InsightStatus.DELETED},
    InsightStatus.IN_PROGRESS: {
        InsightStatus.IN_PROGRESS,
        InsightStatus.OPEN,
        InsightStatus.RESOLVED,
        InsightStatus.DELETED,
    },
    InsightStatus.RESOLVED: {InsightStatus.RESOLVED, InsightStatus.IN_PROGRESS, InsightStatus.DELETED},
    InsightStatus.DELETED: {InsightStatus.DELETED},
}


def _validate_status_transition(current: InsightStatus, requested: InsightStatus) -> None:
    if requested not in _ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: {current.value} → {requested.value}.",
        )


def build_insights_router() -> APIRouter:
    router = APIRouter()
    _filter_dep = make_filter_obj_dep(InsightFilter)

    @router.post(
        "/insights",
        response_model=Insight,
        status_code=201,
        tags=["Insights · Insights"],
    )
    async def create_insight(
        workspace: str,
        body: CreateInsightRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        insight = Insight(
            name=body.name,
            workspace=workspace,
            agent=body.agent,
            description=body.description,
            hypothesis=body.hypothesis,
            impact_estimate=body.impact_estimate,
            eval_dataset_row_refs=body.eval_dataset_row_refs,
            experiment_refs=body.experiment_refs,
        )
        try:
            return await entity_client.create(insight)
        except NemoEntityConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Insight '{body.name}' already exists in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to create insight '%s'", body.name)
            raise HTTPException(status_code=500, detail="Failed to create insight.") from exc

    @router.get(
        "/insights",
        response_model=InsightPage,
        tags=["Insights · Insights"],
    )
    async def list_insights(
        workspace: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        sort: str = Query(default="-created_at"),
        filter: InsightFilter = Depends(_filter_dep),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> InsightPage:
        filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
        try:
            result = await entity_client.list(
                Insight,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
                filter_obj=filter_dict or None,
            )
        except Exception as exc:
            logger.exception("Failed to list insights in workspace '%s'", workspace)
            raise HTTPException(status_code=500, detail="Failed to list insights.") from exc

        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return InsightPage(data=result.data, pagination=pagination, sort=sort, filter=filter)

    @router.get(
        "/insights/{name}",
        response_model=Insight,
        tags=["Insights · Insights"],
    )
    async def get_insight(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        try:
            return await entity_client.get(Insight, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to get insight '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to get insight.") from exc

    @router.patch(
        "/insights/{name}",
        response_model=Insight,
        tags=["Insights · Insights"],
    )
    async def update_insight(
        workspace: str,
        name: str,
        body: UpdateInsightRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        try:
            insight = await entity_client.get(Insight, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{name}' not found in workspace '{workspace}'.",
            ) from exc

        if body.status is not None:
            _validate_status_transition(insight.status, body.status)
            insight.status = body.status
        if body.description is not None:
            insight.description = body.description
        if body.hypothesis is not None:
            insight.hypothesis = body.hypothesis
        if body.impact_estimate is not None:
            insight.impact_estimate = body.impact_estimate
        if body.eval_dataset_row_refs is not None:
            insight.eval_dataset_row_refs = body.eval_dataset_row_refs
        if body.experiment_refs is not None:
            insight.experiment_refs = body.experiment_refs

        try:
            return await entity_client.update(insight)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to update insight '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to update insight.") from exc

    @router.delete(
        "/insights/{name}",
        response_model=Insight,
        tags=["Insights · Insights"],
    )
    async def delete_insight(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> Insight:
        """Soft delete: sets ``status=deleted`` and returns the updated entity."""
        try:
            insight = await entity_client.get(Insight, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Insight '{name}' not found in workspace '{workspace}'.",
            ) from exc

        _validate_status_transition(insight.status, InsightStatus.DELETED)
        insight.status = InsightStatus.DELETED

        try:
            return await entity_client.update(insight)
        except Exception as exc:
            logger.exception("Failed to soft-delete insight '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to delete insight.") from exc

    return router
