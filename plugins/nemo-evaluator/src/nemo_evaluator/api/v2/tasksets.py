# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CRUD routes for stored tasksets under /apis/evaluator/v2/workspaces/{workspace}/tasksets."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from nemo_evaluator.api.dependencies import get_taskset_service
from nemo_evaluator.api.schemas import Taskset, TasksetFilter, TasksetInput, TasksetSort
from nemo_evaluator.api.service.taskset_service import (
    DuplicateTaskRefError,
    TaskRefNotFoundError,
    TasksetExistsError,
    TasksetService,
)
from nemo_evaluator.authz import scope
from nemo_evaluator.entities import MAX_NAME_LENGTH, NAME_PATTERN
from nemo_platform_plugin.api.parsed_filter import ParsedFilter, make_filter_dep
from nemo_platform_plugin.authz import CallerKind, PermissionSet, path_rule, perm
from nemo_platform_plugin.entities import EntityValidationError
from nemo_platform_plugin.jobs.openapi_utils import generate_openapi_extra_params
from nemo_platform_plugin.log_utils import sanitize_for_log
from nemo_platform_plugin.schema import Page

logger = logging.getLogger(__name__)


class TasksetPerms(PermissionSet, namespace="evaluator.tasksets"):
    """Permissions for the stored-taskset CRUD collection."""

    CREATE = perm("Create a stored taskset")
    LIST = perm("List stored tasksets")
    READ = perm("Read a stored taskset")
    DELETE = perm("Delete a stored taskset")


router = APIRouter()


@router.get(
    "/tasksets",
    summary="List Tasksets By Workspace",
    response_description="Return stored tasksets for a workspace",
    status_code=status.HTTP_200_OK,
    response_model=Page[Taskset],
    response_model_exclude_none=True,
    openapi_extra=generate_openapi_extra_params(
        filter_schema=TasksetFilter,
        filter_description="Filter tasksets by workspace, name, created_at, and updated_at.",
    ),
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TasksetPerms.LIST])
async def list_tasksets(
    workspace: str,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size."),
    sort: TasksetSort = Query(
        default=TasksetSort.CREATED_AT_ASC,
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
    ),
    parsed_filter: ParsedFilter = Depends(make_filter_dep(TasksetFilter)),
    service: TasksetService = Depends(get_taskset_service),
) -> Page[Taskset]:
    """List stored tasksets for a specific workspace."""
    # Discard any workspace override in the filter — always scope to the path workspace.
    parsed_filter.remove("workspace")
    try:
        return await service.list_tasksets(
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filter_operation=parsed_filter.operation,
        )
    except Exception:
        logger.exception(f"Failed to list tasksets for workspace {sanitize_for_log(workspace)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post(
    "/tasksets/{name}",
    summary="Create Taskset",
    response_description="Store a new taskset",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Taskset already exists"}},
)
@scope.write
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TasksetPerms.CREATE])
async def create_taskset(
    workspace: str,
    name: Annotated[str, Path(max_length=MAX_NAME_LENGTH, pattern=NAME_PATTERN)],
    taskset: TasksetInput,
    project: str | None = Query(default=None, description="Optional project to associate with the taskset."),
    service: TasksetService = Depends(get_taskset_service),
) -> Taskset:
    """Store a new taskset, addressed by workspace/name."""
    safe_workspace = sanitize_for_log(workspace)
    safe_name = sanitize_for_log(name)
    logger.info(f"Creating taskset: {safe_workspace}/{safe_name}")
    try:
        return await service.create_taskset(name, taskset, workspace=workspace, project=project)
    except EntityValidationError as e:
        logger.warning(f"Entity store validation error during taskset creation: {e}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (TaskRefNotFoundError, DuplicateTaskRefError) as e:
        # A bad member reference (missing task, or two refs to the same task) — a client error.
        logger.warning(f"Taskset has an invalid task reference: {e}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except TasksetExistsError:
        logger.warning(f"Taskset already exists: {safe_workspace}/{safe_name}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Taskset with workspace '{workspace}' and name '{name}' already exists",
        )
    except ValueError as e:
        logger.warning(f"Taskset creation validation error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid taskset data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create taskset")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get(
    "/tasksets/{name}",
    summary="Get Taskset",
    response_description="Return stored taskset details",
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Taskset not found"}},
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TasksetPerms.READ])
async def get_taskset(
    workspace: str,
    name: str,
    service: TasksetService = Depends(get_taskset_service),
) -> Taskset:
    """Get a stored taskset by workspace and name."""
    logger.debug(f"Getting taskset: {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
    # Only the service call can fail unexpectedly; wrap just that so the 404 below is raised outside
    # the try (no catching HTTPException only to re-raise it).
    try:
        taskset = await service.get_taskset(workspace, name)
    except Exception:
        logger.exception(f"Failed to get taskset {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    if not taskset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Taskset not found: {workspace}/{name}")
    return taskset


@router.delete(
    "/tasksets/{name}",
    summary="Delete Taskset",
    response_description="Delete a stored taskset",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Taskset not found"}},
)
@scope.write
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TasksetPerms.DELETE])
async def delete_taskset(
    workspace: str,
    name: str,
    service: TasksetService = Depends(get_taskset_service),
):
    """Delete a stored taskset by workspace and name."""
    logger.info(f"Deleting taskset: {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
    # Wrap only the service call so the 404 below is raised outside the try (no catch-and-re-raise).
    try:
        deleted = await service.delete_taskset(workspace, name)
    except Exception:
        logger.exception(f"Failed to delete taskset {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Taskset not found: {workspace}/{name}")
    return None
