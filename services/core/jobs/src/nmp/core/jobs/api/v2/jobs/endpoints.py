# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job API endpoints."""

import logging
import math
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from nemo_platform import AsyncNeMoPlatform
from nmp.common.api.common import Page, PaginationData
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.api.utils import generate_openapi_extra_params, parse_deep_object
from nmp.common.auth import AuthClient, AuthContext, get_auth_client
from nmp.common.config import get_platform_config
from nmp.common.entities.client import EntityConflictError, EntityValidationError
from nmp.common.jobs.docker import validate_gpu_available_for_docker
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.common.jobs.log_client import JobLogsClient, dep_job_logs_client
from nmp.common.jobs.result_manager import download_from_result_info
from nmp.common.jobs.schemas import (
    InvalidPageCursorError,
    PlatformJobListResultResponse,
    PlatformJobLogPage,
    PlatformJobResultCreateRequest,
    PlatformJobResultResponse,
    PlatformJobStatusResponse,
)
from nmp.common.observability import scoped_app_ctx
from nmp.common.sdk_factory import get_async_platform_sdk
from nmp.common.service.dependencies import get_sdk_client
from nmp.core.jobs.api.dependencies import dep_dispatcher
from nmp.core.jobs.api.v2.jobs.schemas import (
    CreatePlatformJobRequest,
    PlatformJobListTaskResponse,
    PlatformJobResponse,
    PlatformJobsListFilter,
    PlatformJobSortField,
    PlatformJobStatusDetailsUpdateRequest,
    PlatformJobStatusUpdateRequest,
    PlatformJobStepsListFilter,
    PlatformJobStepWithContext,
    PlatformJobTaskUpdate,
)
from nmp.core.jobs.app.ctx import JobContext
from nmp.core.jobs.app.dispatcher import JobDispatcher, StateTransitionConflictError
from nmp.core.jobs.app.profiles import ExecutionProfileT
from nmp.core.jobs.app.providers import CPUExecutionProvider, SubprocessExecutionProvider
from nmp.core.jobs.app.schemas import (
    PlatformJobSpec,
)
from nmp.core.jobs.config import config, profiles
from nmp.core.jobs.entities import PlatformJobStep, PlatformJobTask
from pydantic import ValidationError
from starlette.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter()

platform_config = get_platform_config()


def get_platform_jobs_steps_list_filter(request: Request) -> PlatformJobStepsListFilter:
    """Extract PlatformJobStepsListFilter from request query parameters."""
    try:
        filters = parse_deep_object(name="filter", params=request.query_params) or {}
        return PlatformJobStepsListFilter(**filters)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


def validate_job_spec(
    job_spec: PlatformJobSpec,
    execution_profiles: list[ExecutionProfileT],
) -> None:
    """Validate that the job spec is compatible with the execution profile."""
    for step in job_spec.steps:
        profile_name = step.executor.profile
        execution_profile = next(
            (ep for ep in execution_profiles if ep.provider == step.executor.provider and ep.profile == profile_name),
            None,
        )
        if not execution_profile:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"The execution profile '{step.executor.provider}/{profile_name}' specified in step '{step.name}' does not exist.",
            )

        if step.requires_persistent_storage and not execution_profile.supports_persistent_storage:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"The selected execution profile '{execution_profile}' does not support persistent storage required by step '{step.name}'.",
            )
    try:
        validate_gpu_available_for_docker(job_spec.model_dump())
    except PlatformJobCompilationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        ) from e


def translate_cpu_container_steps_to_subprocess(
    job_spec: PlatformJobSpec,
    subprocess_profiles: set[str],
) -> PlatformJobSpec:
    """Translate CPU container steps when explicitly configured for subprocess compatibility."""
    if not subprocess_profiles:
        return job_spec

    translated_spec = job_spec.model_copy(deep=True)
    for step in translated_spec.steps:
        executor = step.executor
        if not isinstance(executor, CPUExecutionProvider) or executor.profile not in subprocess_profiles:
            continue
        command = [*executor.container.entrypoint, *executor.container.command]
        if not command:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Subprocess execution for step '{step.name}' requires container.entrypoint and/or container.command.",
            )
        step.executor = SubprocessExecutionProvider(provider="subprocess", profile=executor.profile, command=command)
    return translated_spec


def configured_subprocess_translation_profiles() -> set[str]:
    """Return explicitly configured subprocess profiles that should accept CPU container jobs."""
    return {profile.profile for profile in config.executors if profile.provider == "subprocess"}


# Execution Profiles Endpoint
@router.get("/v2/execution-profiles")
async def get_execution_profiles() -> list[ExecutionProfileT]:
    """Get all currently configured execution profiles."""
    return profiles


@router.post(
    "/v2/workspaces/{workspace}/jobs",
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    workspace: str,
    request: CreatePlatformJobRequest,
    auth_client: AuthClient = Depends(get_auth_client),
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> PlatformJobResponse:
    """Create a new platform job."""
    platform_spec = translate_cpu_container_steps_to_subprocess(
        request.platform_spec, configured_subprocess_translation_profiles()
    )
    request = request.model_copy(update={"platform_spec": platform_spec})
    validate_job_spec(request.platform_spec, profiles)

    try:
        return await dispatcher.create_job(
            request,
            workspace,
            auth_context=AuthContext.from_principal(auth_client.principal),
            sdk=sdk,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Unable to create job: {str(e)}")
    except EntityValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.get(
    "/v2/workspaces/{workspace}/jobs",
    response_model=Page[PlatformJobResponse],
    response_model_exclude_none=True,
    openapi_extra=generate_openapi_extra_params(
        filter_schema=PlatformJobsListFilter,
        filter_description="Filter jobs by workspace, project, name, status, source, created_at, and updated_at.",
    ),
    status_code=status.HTTP_200_OK,
)
async def list_jobs(
    workspace: str,
    page: int = Query(default=1, description="Page number.", gt=0),
    page_size: int = Query(default=10, description="Page size.", gt=0),
    sort: PlatformJobSortField = Query(
        default=PlatformJobSortField.CREATED_AT_DESC,
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
    ),
    parsed: ParsedFilter = Depends(make_filter_dep(PlatformJobsListFilter)),
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> Page[PlatformJobResponse]:
    """List platform jobs with filtering and pagination."""

    offset = (page - 1) * page_size
    jobs, total_count = await dispatcher.list_jobs(parsed, workspace, limit=page_size, offset=offset, sort=sort)

    return Page(
        data=jobs,
        pagination=PaginationData(
            page=page,
            page_size=page_size,
            current_page_size=len(jobs),
            total_pages=int(math.ceil(total_count / page_size)) if total_count > 0 else 1,
            total_results=total_count,
        ),
        sort=sort,
        filter=parsed.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/jobs/{name}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def get_job(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobResponse:
    """Get a platform job by name."""
    with scoped_app_ctx(JobContext(id=name)):
        job = await dispatcher.get_job(name, workspace)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job


@router.post(
    "/v2/workspaces/{workspace}/jobs/{name}/cancel",
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def cancel_job(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobResponse:
    """Cancel a platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        try:
            job = await dispatcher.cancel_job(name, workspace)
        except StateTransitionConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job


@router.post(
    "/v2/workspaces/{workspace}/jobs/{name}/pause",
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def pause_job(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobResponse:
    """Pause a platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        job = await dispatcher.pause_job(name, workspace)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job


@router.post(
    "/v2/workspaces/{workspace}/jobs/{name}/resume",
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def resume_job(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobResponse:
    """Resume a paused platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        job = await dispatcher.resume_job(name, workspace)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job


@router.delete(
    "/v2/workspaces/{workspace}/jobs/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def delete_job(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> None:
    """Delete a platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        deleted = await dispatcher.delete_job(name, workspace)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.get(
    "/v2/workspaces/{workspace}/jobs/{name}/status",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def get_job_status(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobStatusResponse:
    """Get the status of a platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        job_status = await dispatcher.get_job_status(name, workspace)
        if not job_status:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return job_status


@router.patch(
    "/v2/workspaces/{workspace}/jobs/{name}/status-details",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def update_job_status_details(
    name: str,
    request: PlatformJobStatusDetailsUpdateRequest,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> None:
    """Update the status details of a platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        result = await dispatcher.update_job_status_details(name, workspace, request)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.get(
    "/v2/workspaces/{workspace}/jobs/{name}/logs",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def page_job_logs(
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
    logs_client: JobLogsClient = Depends(dep_job_logs_client),
    limit: int = Query(default=100, description="Maximum number of logs to return", gt=0),
    page_cursor: str = Query(default=None, description="Page cursor"),
    attempt_id: Optional[int] = Query(default=None, description="Filter logs by job attempt ID"),
    step_id: Optional[str] = Query(default=None, description="Filter logs by step name"),
    task_id: Optional[str] = Query(default=None, description="Filter logs by task ID"),
) -> PlatformJobLogPage:
    """Get paginated logs for a platform job."""
    with scoped_app_ctx(JobContext(id=name)):
        job = await dispatcher.get_job(name, workspace)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        try:
            filters = {
                "job": name,
                "job_attempt": attempt_id if attempt_id is not None else job.attempt_id,
            }
            if step_id:
                filters["job_step"] = step_id
            if task_id:
                filters["job_task"] = task_id
            return await logs_client.query_logs(
                job.fileset, workspace=workspace, filters=filters, page_size=limit, page_cursor=page_cursor
            )
        except InvalidPageCursorError as e:
            logger.error(f"Invalid page cursor: {str(e)}")
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid page cursor")
        except Exception as e:
            logger.error(f"Unexpected error when querying logs: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to query job logs")


# Job Results Endpoints
@router.post(
    "/v2/workspaces/{workspace}/jobs/{job}/results/{name}",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def create_job_result(
    job: str,
    name: str,
    workspace: str,
    request: PlatformJobResultCreateRequest,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobResultResponse:
    """Create a new result for a job."""
    with scoped_app_ctx(JobContext(id=job, result_name=name)):
        job_entity = await dispatcher.get_job(job, workspace)
        if not job_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        result = await dispatcher.create_result(
            job_id=job_entity.id,
            result_name=name,
            workspace=workspace,
            artifact_url=request.artifact_url,
            artifact_storage_type=request.artifact_storage_type,
        )
        return result.to_response()


@router.get(
    "/v2/workspaces/{workspace}/jobs/{name}/results",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Job not Found"},
    },
)
async def list_job_results(
    workspace: str,
    name: str,
    sort: PlatformJobSortField = Query(
        default=PlatformJobSortField.CREATED_AT_DESC,
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
    ),
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobListResultResponse:
    """List results for a job."""
    with scoped_app_ctx(JobContext(id=name)):
        job_entity = await dispatcher.get_job(name, workspace)
        if not job_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        results, _ = await dispatcher.list_results(job_id=job_entity.id, workspace=workspace, sort=sort)
        return PlatformJobListResultResponse(data=[r.to_response() for r in results])


@router.get(
    "/v2/workspaces/{workspace}/jobs/{job}/results/{name}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
    },
)
async def get_job_result(
    job: str,
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobResultResponse:
    """Get a specific job result."""
    with scoped_app_ctx(JobContext(id=job, result_name=name)):
        result = await dispatcher.get_result(job, name, workspace)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job result not found")
        return result.to_response()


@router.get(
    "/v2/workspaces/{workspace}/jobs/{job}/results/{name}/download",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Successful Response",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
    },
    response_class=FileResponse,
)
async def download_job_result(
    job: str,
    name: str,
    workspace: str,
    background_tasks: BackgroundTasks,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> FileResponse:
    """Download a job result file."""
    with scoped_app_ctx(JobContext(id=job, result_name=name)):
        result = await dispatcher.get_result(job, name, workspace)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job result not found")

        filename, tmp_dir_path = await download_from_result_info(
            result_name=name,
            job_name=job,
            workspace=workspace,
            artifact_url=result.artifact_url,
            files_sdk=get_async_platform_sdk(),
        )
        background_tasks.add_task(lambda: tmp_dir_path.cleanup_tmp_dir())
        return FileResponse(path=tmp_dir_path.path, filename=filename, background=background_tasks)


# Job Steps Endpoints
@router.get(
    "/v2/workspaces/{workspace}/jobs/{name}/steps",
    response_model=Page[PlatformJobStepWithContext],
    response_model_exclude_none=True,
    openapi_extra=generate_openapi_extra_params(
        filter_schema=PlatformJobStepsListFilter,
        filter_description="Filter steps by job, status, and source.",
    ),
)
async def list_steps(
    name: str,
    workspace: str,
    page: int = Query(default=1, description="Page number.", gt=0),
    page_size: int = Query(default=25, description="Page size.", gt=0),
    sort: PlatformJobSortField = Query(
        default=PlatformJobSortField.CREATED_AT_ASC,
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
    ),
    filter: PlatformJobStepsListFilter = Depends(get_platform_jobs_steps_list_filter),
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> Page[PlatformJobStepWithContext]:
    """List job steps with pagination and filtering."""
    with scoped_app_ctx(JobContext(id=name)):
        if name != "-":
            filter.job = name

        offset = (page - 1) * page_size
        steps, total_count = await dispatcher.list_steps(
            filter=filter, sort=sort, limit=page_size, offset=offset, workspace=workspace
        )

        dumped = filter.model_dump(mode="json", exclude_none=True)
        return Page(
            data=steps,
            pagination=PaginationData(
                page=page,
                page_size=page_size,
                current_page_size=len(steps),
                total_pages=int(math.ceil(total_count / page_size)) if total_count > 0 else 1,
                total_results=total_count,
            ),
            sort=sort,
            filter=dumped or None,
        )


@router.get(
    "/v2/workspaces/{workspace}/jobs/{job}/steps/{name}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
    },
)
async def get_job_step(
    job: str,
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobStep:
    """Get a specific job step."""
    with scoped_app_ctx(JobContext(id=job, step_name=name)):
        step = await dispatcher.get_current_job_step_by_name(job, name, workspace)
        if not step:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job step not found")
        return step


@router.patch(
    "/v2/workspaces/{workspace}/jobs/{job}/steps/{name}/status",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
        status.HTTP_409_CONFLICT: {"description": "Conflict"},
    },
)
async def update_job_step_status(
    job: str,
    name: str,
    request: PlatformJobStatusUpdateRequest,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobStep:
    """Update a job step status."""
    with scoped_app_ctx(JobContext(id=job, step_name=name)):
        step_entity = await dispatcher.get_current_job_step_by_name(job, name, workspace)
        if not step_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job step not found")

        try:
            step_entity, _ = await dispatcher.update_job_status_from_step(
                step_entity,
                request.status,
                status_details=request.status_details,
                error_details=request.error_details,
            )
        except StateTransitionConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        except EntityConflictError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflict updating job step (entity was modified by another request): {e}",
            )

        return step_entity


# Job Tasks Endpoints
@router.get(
    "/v2/workspaces/{workspace}/jobs/{job}/steps/{name}/tasks",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
    },
)
async def list_job_step_tasks(
    job: str,
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobListTaskResponse:
    """List tasks for a job step."""
    with scoped_app_ctx(JobContext(id=job, step_name=name)):
        job_entity = await dispatcher.get_job(job, workspace)
        if not job_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        step_entity = await dispatcher.get_current_job_step_by_name(job, name, workspace)
        if not step_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job step not found")

        return PlatformJobListTaskResponse(data=await dispatcher.list_tasks(step_entity.id))


@router.put(
    "/v2/workspaces/{workspace}/jobs/{job}/steps/{step}/tasks/{name}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
    },
)
async def update_job_step_task(
    job: str,
    step: str,
    name: str,
    update: PlatformJobTaskUpdate,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobTask:
    """Update a job step task."""
    with scoped_app_ctx(JobContext(id=job, step_name=step)):
        step_entity = await dispatcher.get_current_job_step_by_name(job, step, workspace)
        if not step_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job step not found")

        return await dispatcher.create_or_update_task(
            job,
            name,
            workspace,
            update,
            step_entity,
        )


@router.get(
    "/v2/workspaces/{workspace}/jobs/{job}/steps/{step}/tasks/{name}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Successful Response"},
        status.HTTP_404_NOT_FOUND: {"description": "Not Found"},
    },
)
async def get_job_step_task(
    job: str,
    step: str,
    name: str,
    workspace: str,
    dispatcher: JobDispatcher = Depends(dep_dispatcher),
) -> PlatformJobTask:
    """Get a specific job step task."""
    with scoped_app_ctx(JobContext(id=job, step_name=step, task_id=name)):
        step_entity = await dispatcher.get_current_job_step_by_name(job, step, workspace)
        if not step_entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job step not found")

        task = await dispatcher.get_task(step_entity.id, name, workspace)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job step task not found")
        return task
