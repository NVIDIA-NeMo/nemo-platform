# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Volume CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_deployments_plugin.api.v2.dependencies import get_entity_client
from nemo_deployments_plugin.entities import Volume
from nemo_deployments_plugin.references import deployment_config_names_referencing_volume
from nemo_deployments_plugin.schema import CreateVolumeRequest, VolumeFilter, VolumePage
from nemo_platform_plugin.api.filters import make_filter_obj_dep
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError, NemoEntityNotFoundError
from nemo_platform_plugin.schema import PaginationData

router = APIRouter()

_volume_filter_dep = make_filter_obj_dep(VolumeFilter)


@router.post("/volumes", response_model=Volume, status_code=201, tags=["Volumes"])
async def create_volume(
    workspace: str,
    body: CreateVolumeRequest,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> Volume:
    volume = Volume(
        name=body.name,
        workspace=workspace,
        status="PENDING",
        **body.model_dump(exclude={"name"}, exclude_none=True),
    )
    try:
        return await entity_client.create(volume)
    except NemoEntityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Volume '{body.name}' already exists in workspace '{workspace}'.",
        ) from exc


@router.get("/volumes", response_model=VolumePage, tags=["Volumes"])
async def list_volumes(
    workspace: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-created_at"),
    filter: VolumeFilter = Depends(_volume_filter_dep),
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> VolumePage:
    filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
    result = await entity_client.list(
        Volume,
        workspace=workspace,
        page=page,
        page_size=page_size,
        sort=sort,
        filter_obj=filter_dict or None,
    )
    pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
    return VolumePage(data=result.data, pagination=pagination, sort=sort, filter=filter)


@router.get("/volumes/{name}", response_model=Volume, tags=["Volumes"])
async def get_volume(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> Volume:
    try:
        return await entity_client.get(Volume, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Volume '{name}' not found in workspace '{workspace}'.",
        ) from exc


@router.delete("/volumes/{name}", status_code=204, tags=["Volumes"])
async def delete_volume(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> None:
    referencing = await deployment_config_names_referencing_volume(
        entity_client,
        workspace=workspace,
        volume_name=name,
    )
    if referencing:
        joined = ", ".join(referencing)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Volume '{name}' is referenced by deployment-config(s): {joined}. "
                "Remove volume mounts from those configs first."
            ),
        )

    try:
        await entity_client.delete(Volume, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Volume '{name}' not found in workspace '{workspace}'.",
        ) from exc
