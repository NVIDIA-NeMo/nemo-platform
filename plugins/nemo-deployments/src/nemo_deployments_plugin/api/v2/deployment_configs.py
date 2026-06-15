# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""DeploymentConfig CRUD routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_deployments_plugin.api.v2.dependencies import get_entity_client
from nemo_deployments_plugin.entities import DeploymentConfig
from nemo_deployments_plugin.references import deployment_names_using_config
from nemo_deployments_plugin.schema import (
    CreateDeploymentConfigRequest,
    DeploymentConfigFilter,
    DeploymentConfigPage,
)
from nemo_deployments_plugin.validation import (
    PrerequisiteCycleError,
    build_existing_prerequisite_map,
    detect_prerequisite_cycle,
    prerequisite_names,
)
from nemo_platform_plugin.api.filters import make_filter_obj_dep
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError, NemoEntityNotFoundError
from nemo_platform_plugin.schema import PaginationData

logger = logging.getLogger(__name__)

router = APIRouter()

_config_filter_dep = make_filter_obj_dep(DeploymentConfigFilter)


async def _list_all_deployment_configs(
    entity_client: NemoEntitiesClient,
    workspace: str,
) -> list[DeploymentConfig]:
    """Page through all deployment configs for prerequisite graph validation."""
    page = 1
    configs: list[DeploymentConfig] = []
    while True:
        result = await entity_client.list(
            DeploymentConfig,
            workspace=workspace,
            page=page,
            page_size=100,
        )
        configs.extend(result.data)
        if result.pagination is None or page >= result.pagination.total_pages:
            break
        page += 1
    return configs


@router.post("/deployment-configs", response_model=DeploymentConfig, status_code=201, tags=["Deployment Configs"])
async def create_deployment_config(
    workspace: str,
    body: CreateDeploymentConfigRequest,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> DeploymentConfig:
    prereq_names = prerequisite_names(body.prerequisites)
    try:
        existing_configs = await _list_all_deployment_configs(entity_client, workspace)
        existing_map = build_existing_prerequisite_map(existing_configs)
        detect_prerequisite_cycle(
            config_name=body.name,
            prerequisites=prereq_names,
            existing=existing_map,
        )
    except PrerequisiteCycleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = DeploymentConfig(
        name=body.name,
        workspace=workspace,
        **body.model_dump(exclude={"name"}, exclude_none=True),
    )
    try:
        return await entity_client.create(config)
    except NemoEntityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"DeploymentConfig '{body.name}' already exists in workspace '{workspace}'.",
        ) from exc


@router.get("/deployment-configs", response_model=DeploymentConfigPage, tags=["Deployment Configs"])
async def list_deployment_configs(
    workspace: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-created_at"),
    filter: DeploymentConfigFilter = Depends(_config_filter_dep),
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> DeploymentConfigPage:
    filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
    result = await entity_client.list(
        DeploymentConfig,
        workspace=workspace,
        page=page,
        page_size=page_size,
        sort=sort,
        filter_obj=filter_dict or None,
    )
    pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
    return DeploymentConfigPage(data=result.data, pagination=pagination, sort=sort, filter=filter)


@router.get("/deployment-configs/{name}", response_model=DeploymentConfig, tags=["Deployment Configs"])
async def get_deployment_config(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> DeploymentConfig:
    try:
        return await entity_client.get(DeploymentConfig, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"DeploymentConfig '{name}' not found in workspace '{workspace}'.",
        ) from exc


@router.delete("/deployment-configs/{name}", status_code=204, tags=["Deployment Configs"])
async def delete_deployment_config(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> None:
    # Best-effort referential check before delete. Entity store has no conditional
    # delete API today, so this cannot be fully atomic against concurrent creates.
    referencing = await deployment_names_using_config(
        entity_client,
        workspace=workspace,
        config_name=name,
    )
    if referencing:
        joined = ", ".join(referencing)
        raise HTTPException(
            status_code=409,
            detail=(
                f"DeploymentConfig '{name}' is referenced by deployment(s): {joined}. Delete those deployments first."
            ),
        )

    try:
        await entity_client.delete(DeploymentConfig, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"DeploymentConfig '{name}' not found in workspace '{workspace}'.",
        ) from exc
