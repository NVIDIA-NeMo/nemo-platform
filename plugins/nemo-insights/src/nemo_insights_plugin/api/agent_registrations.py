# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI routes for AgentRegistration CRUD."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_insights_plugin.entities import AgentRegistration
from nemo_insights_plugin.schema import (
    AgentRegistrationFilter,
    AgentRegistrationPage,
    CreateAgentRegistrationRequest,
    UpdateAgentRegistrationRequest,
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


def build_agent_registrations_router() -> APIRouter:
    router = APIRouter()
    _filter_dep = make_filter_obj_dep(AgentRegistrationFilter)

    @router.post(
        "/agent_registrations",
        response_model=AgentRegistration,
        status_code=201,
        tags=["Insights · Agent Registrations"],
    )
    async def create_agent_registration(
        workspace: str,
        body: CreateAgentRegistrationRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AgentRegistration:
        uploaded_at = datetime.now(timezone.utc) if body.agent_description_content else None
        reg = AgentRegistration(
            name=body.name,
            workspace=workspace,
            description=body.description,
            repo_url=body.repo_url,
            agent_description_path=body.agent_description_path,
            agent_description_content=body.agent_description_content,
            agent_description_uploaded_at=uploaded_at,
            eval_command=body.eval_command,
            cloud_agent_type=body.cloud_agent_type,
            cloud_agent_config=body.cloud_agent_config,
        )
        try:
            return await entity_client.create(reg)
        except NemoEntityConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"AgentRegistration '{body.name}' already exists in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to create agent_registration '%s'", body.name)
            raise HTTPException(status_code=500, detail="Failed to create agent_registration.") from exc

    @router.get(
        "/agent_registrations",
        response_model=AgentRegistrationPage,
        tags=["Insights · Agent Registrations"],
    )
    async def list_agent_registrations(
        workspace: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        sort: str = Query(default="-created_at"),
        filter: AgentRegistrationFilter = Depends(_filter_dep),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AgentRegistrationPage:
        filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
        try:
            result = await entity_client.list(
                AgentRegistration,
                workspace=workspace,
                page=page,
                page_size=page_size,
                sort=sort,
                filter_obj=filter_dict or None,
            )
        except Exception as exc:
            logger.exception("Failed to list agent_registrations in workspace '%s'", workspace)
            raise HTTPException(status_code=500, detail="Failed to list agent_registrations.") from exc

        pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
        return AgentRegistrationPage(data=result.data, pagination=pagination, sort=sort, filter=filter)

    @router.get(
        "/agent_registrations/{name}",
        response_model=AgentRegistration,
        tags=["Insights · Agent Registrations"],
    )
    async def get_agent_registration(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AgentRegistration:
        try:
            return await entity_client.get(AgentRegistration, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"AgentRegistration '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to get agent_registration '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to get agent_registration.") from exc

    @router.patch(
        "/agent_registrations/{name}",
        response_model=AgentRegistration,
        tags=["Insights · Agent Registrations"],
    )
    async def update_agent_registration(
        workspace: str,
        name: str,
        body: UpdateAgentRegistrationRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> AgentRegistration:
        try:
            reg = await entity_client.get(AgentRegistration, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"AgentRegistration '{name}' not found in workspace '{workspace}'.",
            ) from exc

        if body.description is not None:
            reg.description = body.description
        if body.repo_url is not None:
            reg.repo_url = body.repo_url
        if body.agent_description_path is not None:
            reg.agent_description_path = body.agent_description_path
        if body.agent_description_content is not None:
            reg.agent_description_content = body.agent_description_content
            reg.agent_description_uploaded_at = datetime.now(timezone.utc)
        if body.eval_command is not None:
            reg.eval_command = body.eval_command
        if body.cloud_agent_type is not None:
            reg.cloud_agent_type = body.cloud_agent_type
        if body.cloud_agent_config is not None:
            reg.cloud_agent_config = body.cloud_agent_config

        try:
            return await entity_client.update(reg)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"AgentRegistration '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to update agent_registration '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to update agent_registration.") from exc

    @router.delete(
        "/agent_registrations/{name}",
        status_code=204,
        tags=["Insights · Agent Registrations"],
    )
    async def delete_agent_registration(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> None:
        try:
            await entity_client.delete(AgentRegistration, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"AgentRegistration '{name}' not found in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to delete agent_registration '%s'", name)
            raise HTTPException(status_code=500, detail="Failed to delete agent_registration.") from exc

    return router
