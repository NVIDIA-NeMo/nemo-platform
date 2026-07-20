# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrails config endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from nmp.common.api import ParsedFilter, make_filter_dep
from nmp.common.api.common import DeleteResponse, GenericSortField, Page, PaginationData
from nmp.common.api.utils import generate_openapi_extra_params
from nmp.common.entities import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.common.service.dependencies import get_entity_client
from nmp.guardrails.api.dependencies import ConfigRegistryDep, RailsRegistryDep
from nmp.guardrails.api.v2.configs.schemas import GuardrailConfigFilter, GuardrailConfigInput, GuardrailConfigUpdate
from nmp.guardrails.app.utils.config_utils import enrich_config_with_data, invalidate_and_reload_config_cache
from nmp.guardrails.entities import GuardrailConfig

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get(
    "/v2/workspaces/{workspace}/configs",
    response_model=Page[GuardrailConfig],
    response_model_exclude_none=True,
    openapi_extra=generate_openapi_extra_params(
        filter_schema=GuardrailConfigFilter,
        filter_description=("Filter guardrail configs by name, description, project, created_at, and updated_at."),
    ),
)
async def list_guardrail_configs(
    workspace: str,
    entities_client: EntityClient = Depends(get_entity_client),
    page: int = Query(default=1, description="Page number."),
    page_size: int = Query(default=10, description="Page size."),
    sort: GenericSortField = Query(
        default="created_at",
        description="""The field to sort by. To sort in decreasing order, use `-` in front of the field name.""",
    ),
    parsed: ParsedFilter = Depends(make_filter_dep(GuardrailConfigFilter)),
) -> Page[GuardrailConfig]:
    """List available guardrail configs.

    Lists guardrail configs for a specific workspace.
    """
    res = await entities_client.list(
        GuardrailConfig,
        page=page,
        page_size=page_size,
        sort=sort.value,
        workspace=workspace,
        filter_operation=parsed.operation,
    )

    enriched_configs = [enrich_config_with_data(config) for config in res.data]

    return Page(
        data=enriched_configs,
        pagination=PaginationData(
            page=res.pagination.page,
            page_size=res.pagination.page_size,
            current_page_size=len(enriched_configs),
            total_pages=res.pagination.total_pages,
            total_results=res.pagination.total_results,
        ),
        sort=sort,
    )


@router.post(
    "/v2/workspaces/{workspace}/configs",
    status_code=201,
    responses={
        201: {"description": "Config created successfully."},
        422: {"description": "Validation Error"},
        409: {"description": "Config already exists."},
    },
    response_model=GuardrailConfig,
)
async def create_config(
    workspace: str,
    config: GuardrailConfigInput,
    entities_client: EntityClient = Depends(get_entity_client),
) -> GuardrailConfig:
    """Create a new guardrail config."""
    # Check if config already exists
    try:
        existing = await entities_client.get(GuardrailConfig, name=config.name, workspace=workspace)
        if existing:
            raise HTTPException(status_code=409, detail=f"Config '{config.name}' already exists.")
    except EntityNotFoundError:
        pass  # Config doesn't exist, we can create it

    entity = GuardrailConfig(
        name=config.name,
        workspace=workspace,
        description=config.description,
        data=config.data,
    )

    try:
        return await entities_client.create(entity)
    except EntityConflictError:
        raise HTTPException(status_code=409, detail=f"Config '{config.name}' already exists.")


@router.get(
    "/v2/workspaces/{workspace}/configs/{name}",
    responses={
        200: {"description": "Successful Response"},
        404: {"description": "Config does not exist."},
        422: {"description": "Validation Error"},
    },
    response_model=GuardrailConfig,
    response_model_exclude_none=True,
)
async def get_guardrail_config(
    workspace: str,
    name: str,
    entities_client: EntityClient = Depends(get_entity_client),
) -> GuardrailConfig:
    """Get info about a guardrail configuration."""
    try:
        config = await entities_client.get(GuardrailConfig, name=name, workspace=workspace)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Guardrail config not found.")

    return enrich_config_with_data(config)


@router.patch(
    "/v2/workspaces/{workspace}/configs/{name}",
    responses={
        200: {"description": "Successful Response"},
        404: {"description": "Config does not exist."},
        422: {"description": "Validation Error"},
    },
    response_model=GuardrailConfig,
)
async def update_config(
    workspace: str,
    name: str,
    config_data: GuardrailConfigUpdate,
    entities_client: EntityClient = Depends(get_entity_client),
    rails_registry: RailsRegistryDep = None,
    config_registry: ConfigRegistryDep = None,
) -> GuardrailConfig:
    """
    Update model metadata. If the request body has an empty field,
    keep the old value.
    """
    try:
        existing_config = await entities_client.get(GuardrailConfig, name=name, workspace=workspace)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Guardrail config not found.")

    # Apply updates
    diff = config_data.model_dump(include=config_data.model_fields_set, exclude_unset=True)
    config_to_update = existing_config.model_copy(update=diff)

    updated_config = await entities_client.update(config_to_update)

    full_config_id = f"{workspace}/{existing_config.name}" if workspace else existing_config.name

    if config_registry:
        await config_registry.refresh_all()

    if rails_registry:
        invalidate_and_reload_config_cache(
            rails_registry=rails_registry,
            config_id=full_config_id,
        )

    return updated_config


@router.delete(
    "/v2/workspaces/{workspace}/configs/{name}",
    responses={
        200: {"description": "Successful model deletion."},
        404: {"description": "Config does not exist."},
        422: {"description": ("Unable to delete config due to validation error while processing request.")},
    },
)
async def delete_config(
    workspace: str,
    name: str,
    entities_client: EntityClient = Depends(get_entity_client),
    rails_registry: RailsRegistryDep = None,
    config_registry: ConfigRegistryDep = None,
) -> DeleteResponse:
    """Delete a guardrail config."""
    try:
        config = await entities_client.get(GuardrailConfig, name=name, workspace=workspace)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Guardrail config not found.")

    await entities_client.delete(GuardrailConfig, config.name, workspace=workspace)

    full_config_id = f"{workspace}/{config.name}" if workspace else config.name

    if config_registry:
        await config_registry.refresh_all()

    if rails_registry:
        invalidate_and_reload_config_cache(
            rails_registry=rails_registry,
            config_id=full_config_id,
        )

    return DeleteResponse(id=config.id)
