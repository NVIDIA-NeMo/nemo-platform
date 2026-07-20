# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CRUD routes for stored agent-eval tasks under /apis/evaluator/v2/workspaces/{workspace}/tasks."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from nemo_evaluator.api.dependencies import get_task_service
from nemo_evaluator.api.schemas import Task, TaskFilter, TaskInput, TaskSort
from nemo_evaluator.api.service.task_service import MetricRefNotFoundError, TaskService
from nemo_evaluator.authz import scope
from nemo_evaluator.entities import MAX_NAME_LENGTH, NAME_PATTERN
from nemo_platform_plugin.api.parsed_filter import ParsedFilter, make_filter_dep
from nemo_platform_plugin.authz import CallerKind, PermissionSet, path_rule, perm
from nemo_platform_plugin.entities import EntityValidationError
from nemo_platform_plugin.jobs.openapi_utils import generate_openapi_extra_params
from nemo_platform_plugin.log_utils import sanitize_for_log
from nemo_platform_plugin.schema import Page

logger = logging.getLogger(__name__)


class TaskPerms(PermissionSet, namespace="evaluator.tasks"):
    """Permissions for the stored-task CRUD collection."""

    CREATE = perm("Create a stored task")
    LIST = perm("List stored tasks")
    READ = perm("Read a stored task")
    DELETE = perm("Delete a stored task")


router = APIRouter()


@router.get(
    "/tasks",
    summary="List Tasks By Workspace",
    response_description="Return stored tasks for a workspace",
    status_code=status.HTTP_200_OK,
    response_model=Page[Task],
    response_model_exclude_none=True,
    openapi_extra=generate_openapi_extra_params(
        filter_schema=TaskFilter,
        filter_description="Filter tasks by workspace, name, created_at, and updated_at.",
    ),
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TaskPerms.LIST])
async def list_tasks(
    workspace: str,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size."),
    sort: TaskSort = Query(
        default=TaskSort.CREATED_AT_ASC,
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
    ),
    parsed_filter: ParsedFilter = Depends(make_filter_dep(TaskFilter)),
    service: TaskService = Depends(get_task_service),
) -> Page[Task]:
    """List stored tasks for a specific workspace."""
    # Discard any workspace override in the filter — always scope to the path workspace.
    parsed_filter.remove("workspace")
    try:
        return await service.list_tasks(
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filter_operation=parsed_filter.operation,
        )
    except Exception:
        logger.exception(f"Failed to list tasks for workspace {sanitize_for_log(workspace)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post(
    "/tasks/{name}",
    summary="Create Task",
    response_description="Store a new task",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Task already exists"}},
)
@scope.write
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TaskPerms.CREATE])
async def create_task(
    workspace: str,
    name: Annotated[str, Path(max_length=MAX_NAME_LENGTH, pattern=NAME_PATTERN)],
    task: TaskInput,
    project: str | None = Query(default=None, description="Optional project to associate with the task."),
    service: TaskService = Depends(get_task_service),
) -> Task:
    """Store a new task, addressed by workspace/name."""
    safe_workspace = sanitize_for_log(workspace)
    safe_name = sanitize_for_log(name)
    logger.info(f"Creating task: {safe_workspace}/{safe_name}")
    try:
        return await service.create_task(name, task, workspace=workspace, project=project)
    except EntityValidationError as e:
        logger.warning(f"Entity store validation error during task creation: {e}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except MetricRefNotFoundError as e:
        logger.warning(f"Task has an invalid metric reference: {e}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        if "already exists" in str(e).lower():
            logger.warning(f"Task already exists: {safe_workspace}/{safe_name}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Task with workspace '{workspace}' and name '{name}' already exists",
            )
        logger.warning(f"Task creation validation error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create task")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get(
    "/tasks/{name}",
    summary="Get Task",
    response_description="Return stored task details",
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Task not found"}},
)
@scope.read
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TaskPerms.READ])
async def get_task(
    workspace: str,
    name: str,
    service: TaskService = Depends(get_task_service),
) -> Task:
    """Get a stored task by workspace and name."""
    logger.debug(f"Getting task: {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
    try:
        task = await service.get_task(workspace, name)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task not found: {workspace}/{name}",
            )
        return task
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to get task {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.delete(
    "/tasks/{name}",
    summary="Delete Task",
    response_description="Delete a stored task",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Task not found"}},
)
@scope.write
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[TaskPerms.DELETE])
async def delete_task(
    workspace: str,
    name: str,
    service: TaskService = Depends(get_task_service),
):
    """Delete a stored task by workspace and name."""
    logger.info(f"Deleting task: {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
    try:
        deleted = await service.delete_task(workspace, name)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task not found: {workspace}/{name}",
            )
        return None
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to delete task {sanitize_for_log(workspace)}/{sanitize_for_log(name)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
