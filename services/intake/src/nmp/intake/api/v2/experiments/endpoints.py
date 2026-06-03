# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Create, list, get, and delete endpoints for Experiments and ExperimentGroups.

Entity-store (Postgres) operations wired directly onto ``EntityClient``, following
the inline pattern used by the core services. PUT updates only the mutable fields
(group membership, summary, description, metadata); an Experiment's identity and the
dataset/agent it ran against are fixed and changing them is rejected. Rollup fields on
the read models are hydrated from ClickHouse in a later PR; for now they return defaults.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nmp.common.api.common import Page, PaginationData
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.api.utils import generate_openapi_extra_params
from nmp.common.entities.client import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.common.service.dependencies import get_entity_client
from nmp.intake.api.v2.experiments.schemas import (
    ExperimentFilter,
    ExperimentGroupFilter,
    ExperimentGroupRequest,
    ExperimentGroupResponse,
    ExperimentRequest,
    ExperimentResponse,
)
from nmp.intake.entities.experiments import Experiment, ExperimentGroup
from nmp.intake.spans.api.dependencies import require_workspace_access, validate_list_query_params

router = APIRouter(dependencies=[Depends(require_workspace_access)])

GROUPS_TAG = "Experiment Groups"
EXPERIMENTS_TAG = "Experiments"

SortField = Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"]

EntityClientDep = Annotated[EntityClient, Depends(get_entity_client)]
ExperimentGroupFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(ExperimentGroupFilter))]
ExperimentFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(ExperimentFilter))]


# =============================================================================
# Experiment Groups
# =============================================================================


@router.post(
    "/v2/workspaces/{workspace}/experiment-groups",
    response_model=ExperimentGroupResponse,
    status_code=status.HTTP_201_CREATED,
    tags=[GROUPS_TAG],
    responses={409: {"description": "Experiment group already exists"}},
)
async def create_experiment_group(
    workspace: str,
    body: ExperimentGroupRequest,
    entity_client: EntityClientDep,
) -> ExperimentGroupResponse:
    entity = ExperimentGroup(workspace=workspace, name=body.name, description=body.description)
    try:
        created = await entity_client.create(entity)
    except EntityConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment group '{workspace}/{body.name}' already exists.",
        ) from e
    return ExperimentGroupResponse.from_entity(created)


@router.get(
    "/v2/workspaces/{workspace}/experiment-groups",
    response_model=Page[ExperimentGroupResponse],
    tags=[GROUPS_TAG],
    openapi_extra=generate_openapi_extra_params(
        filter_schema=ExperimentGroupFilter,
        filter_description="Filter experiment groups by name.",
    ),
)
async def list_experiment_groups(
    workspace: str,
    request: Request,
    entity_client: EntityClientDep,
    parsed: ExperimentGroupFilterDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size."),
    sort: SortField = Query(default="-created_at", description="Sort field; prefix with '-' for descending."),
) -> Page[ExperimentGroupResponse]:
    validate_list_query_params(request)
    result = await entity_client.list(
        ExperimentGroup,
        workspace=workspace,
        filter_operation=parsed.operation,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page(
        data=[ExperimentGroupResponse.from_entity(e) for e in result.data],
        pagination=PaginationData(**result.pagination.model_dump()),
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/experiment-groups/{name}",
    response_model=ExperimentGroupResponse,
    tags=[GROUPS_TAG],
    responses={404: {"description": "Experiment group not found"}},
)
async def get_experiment_group(
    workspace: str,
    name: str,
    entity_client: EntityClientDep,
) -> ExperimentGroupResponse:
    try:
        entity = await entity_client.get(ExperimentGroup, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment group '{workspace}/{name}' not found.",
        ) from e
    return ExperimentGroupResponse.from_entity(entity)


@router.put(
    "/v2/workspaces/{workspace}/experiment-groups/{name}",
    response_model=ExperimentGroupResponse,
    tags=[GROUPS_TAG],
    responses={
        404: {"description": "Experiment group not found"},
        409: {"description": "Attempt to rename the group"},
    },
)
async def update_experiment_group(
    workspace: str,
    name: str,
    body: ExperimentGroupRequest,
    entity_client: EntityClientDep,
) -> ExperimentGroupResponse:
    try:
        existing = await entity_client.get(ExperimentGroup, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment group '{workspace}/{name}' not found.",
        ) from e
    if body.name != name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rename an experiment group; the name is its identity.",
        )
    existing.description = body.description
    updated = await entity_client.update(existing)
    return ExperimentGroupResponse.from_entity(updated)


@router.delete(
    "/v2/workspaces/{workspace}/experiment-groups/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[GROUPS_TAG],
    responses={404: {"description": "Experiment group not found"}},
)
async def delete_experiment_group(
    workspace: str,
    name: str,
    entity_client: EntityClientDep,
) -> None:
    try:
        await entity_client.delete(ExperimentGroup, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment group '{workspace}/{name}' not found.",
        ) from e


# =============================================================================
# Experiments
# =============================================================================


@router.post(
    "/v2/workspaces/{workspace}/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=[EXPERIMENTS_TAG],
    responses={409: {"description": "Experiment already exists"}},
)
async def create_experiment(
    workspace: str,
    body: ExperimentRequest,
    entity_client: EntityClientDep,
) -> ExperimentResponse:
    entity = Experiment(
        workspace=workspace,
        name=body.name,
        experiment_group_id=body.experiment_group_id,
        agent_name=body.agent_name,
        agent_version=body.agent_version,
        dataset_name=body.dataset_name,
        dataset_version=body.dataset_version,
        source_link=body.source_link,
        metadata=body.metadata,
        description=body.description,
        summary=body.summary,
    )
    try:
        created = await entity_client.create(entity)
    except EntityConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Experiment '{workspace}/{body.name}' already exists.",
        ) from e
    return ExperimentResponse.from_entity(created)


@router.get(
    "/v2/workspaces/{workspace}/experiments",
    response_model=Page[ExperimentResponse],
    tags=[EXPERIMENTS_TAG],
    openapi_extra=generate_openapi_extra_params(
        filter_schema=ExperimentFilter,
        filter_description="Filter experiments by name, experiment_group_id, agent_name, and dataset_name.",
    ),
)
async def list_experiments(
    workspace: str,
    request: Request,
    entity_client: EntityClientDep,
    parsed: ExperimentFilterDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size."),
    sort: SortField = Query(default="-created_at", description="Sort field; prefix with '-' for descending."),
) -> Page[ExperimentResponse]:
    validate_list_query_params(request)
    result = await entity_client.list(
        Experiment,
        workspace=workspace,
        filter_operation=parsed.operation,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page(
        data=[ExperimentResponse.from_entity(e) for e in result.data],
        pagination=PaginationData(**result.pagination.model_dump()),
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/experiments/{name}",
    response_model=ExperimentResponse,
    tags=[EXPERIMENTS_TAG],
    responses={404: {"description": "Experiment not found"}},
)
async def get_experiment(
    workspace: str,
    name: str,
    entity_client: EntityClientDep,
) -> ExperimentResponse:
    try:
        entity = await entity_client.get(Experiment, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{workspace}/{name}' not found.",
        ) from e
    return ExperimentResponse.from_entity(entity)


# Identity and the dataset/agent it was run against are fixed for the life of an
# Experiment (see the ingest invariants); changing them means it's a different
# Experiment. PUT may only edit group membership, source link, summary, description, metadata.
_IMMUTABLE_EXPERIMENT_FIELDS = ("name", "agent_name", "agent_version", "dataset_name", "dataset_version")


@router.put(
    "/v2/workspaces/{workspace}/experiments/{name}",
    response_model=ExperimentResponse,
    tags=[EXPERIMENTS_TAG],
    responses={
        404: {"description": "Experiment not found"},
        409: {"description": "Attempt to change an immutable field"},
    },
)
async def update_experiment(
    workspace: str,
    name: str,
    body: ExperimentRequest,
    entity_client: EntityClientDep,
) -> ExperimentResponse:
    try:
        existing = await entity_client.get(Experiment, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{workspace}/{name}' not found.",
        ) from e

    changed = [f for f in _IMMUTABLE_EXPERIMENT_FIELDS if getattr(body, f) != getattr(existing, f)]
    if changed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot change immutable field(s) {changed} on an existing experiment; "
                "create a new experiment instead."
            ),
        )

    existing.experiment_group_id = body.experiment_group_id
    existing.source_link = body.source_link
    existing.metadata = body.metadata
    existing.description = body.description
    existing.summary = body.summary
    updated = await entity_client.update(existing)
    return ExperimentResponse.from_entity(updated)


@router.delete(
    "/v2/workspaces/{workspace}/experiments/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[EXPERIMENTS_TAG],
    responses={404: {"description": "Experiment not found"}},
)
async def delete_experiment(
    workspace: str,
    name: str,
    entity_client: EntityClientDep,
) -> None:
    try:
        await entity_client.delete(Experiment, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{workspace}/{name}' not found.",
        ) from e
