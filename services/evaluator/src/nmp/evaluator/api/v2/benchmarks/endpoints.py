# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import textwrap
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.routing import APIRoute
from nemo_evaluator_sdk.values import RowScore
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.entities import EntityClient
from nemo_platform_plugin.jobs.api_factory import (
    FileResultSerializer,
    PlatformJobResultRoute,
    PlatformJobSpec,
    PydanticJSONLResultSerializer,
    PydanticResultSerializer,
    job_route_factory,
)
from nmp.common.api.common import DeleteResponse, Page, PaginationData
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.entities import SYSTEM_WORKSPACE
from nmp.common.service.dependencies import get_entity_client, get_sdk_client
from nmp.evaluator.api.v2.benchmarks.manager import (
    BenchmarkCreationError,
    BenchmarkDeletionError,
    BenchmarkRetrievalError,
    BenchmarksManager,
)
from nmp.evaluator.api.v2.benchmarks.schemas.benchmarks import (
    Benchmark,
    BenchmarkJobResult,
    BenchmarkJobResultsListFilter,
    BenchmarkJobResultsListResponse,
    BenchmarkRequest,
    BenchmarksListFilter,
    BenchmarksListResponse,
    ExtendedBenchmark,
    SystemBenchmark,
)
from nmp.evaluator.api.v2.benchmarks.schemas.jobs import BenchmarkJob
from nmp.evaluator.api.v2.common.query_params import AggregateFieldsQuery, validate_list_query_params
from nmp.evaluator.api.v2.common.schemas import ErrorResponse
from nmp.evaluator.app.jobs.constants import (
    JOB_RESULTS_AGGREGATE_SCORES,
    JOB_RESULTS_ROW_SCORES,
    JOBS_RESULTS_ARTIFACTS,
)
from nmp.evaluator.app.values import BenchmarkEvaluationResult

_logger = logging.getLogger(__name__)
router = APIRouter()

API_TAG = "Evaluator"


def get_benchmarks_manager(entity_client: Annotated[EntityClient, Depends(get_entity_client)]) -> BenchmarksManager:
    return BenchmarksManager(entity_client)


BenchmarksManagerDep = Annotated[BenchmarksManager, Depends(get_benchmarks_manager)]
SdkDep = Annotated[AsyncNeMoPlatform, Depends(get_sdk_client)]
BenchmarksFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(BenchmarksListFilter))]
BenchmarkJobResultsFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(BenchmarkJobResultsListFilter))]


# =============================================================================
# /v2/workspaces/{workspace}/benchmark-jobs
# =============================================================================


async def platform_job_config_compiler(
    workspace: str,
    original_spec: BenchmarkJob,
    transformed_spec: BenchmarkJob,
    entity_client: EntityClient,
    job_name: str | None,
    sdk: AsyncNeMoPlatform,
) -> PlatformJobSpec:
    """Compile a benchmark job spec to a platform job spec.

    This function provides exception mapping for the manager's compile_job method.

    Args:
        workspace: The workspace for this job.
        original_spec: The user-provided input specification.
        transformed_spec: The spec after applying the input-to-output transformer.
            Since no transformer is configured for benchmarks, original_spec
            and transformed_spec are identical (both BenchmarkJob).
        entity_client: Entity client for lookups.
        job_name: The resolved job name (user-provided or auto-generated).
        sdk: SDK instance for accessing secrets with user context.
    """
    benchmarks_manager = get_benchmarks_manager(entity_client)

    try:
        return await benchmarks_manager.compile_job(workspace, transformed_spec, sdk=sdk)
    except BenchmarkRetrievalError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    except (KeyError, ValueError, AssertionError, RuntimeError) as e:
        detail = str(e) or f"Job compilation failed: {type(e).__name__}"
        raise HTTPException(status_code=422, detail=detail) from e


_jobs_router = job_route_factory(
    # Use distinct job sources to prevent mixing incompatible job specs when listing.
    # (MetricEvaluation and BenchmarkEvaluation jobs have different spec schemas.)
    service_name="evaluator-benchmarks",
    job_type="BenchmarkEvaluation",
    job_input=BenchmarkJob,
    platform_job_config_compiler=platform_job_config_compiler,
    job_result_routes=[
        PlatformJobResultRoute(
            name=JOB_RESULTS_AGGREGATE_SCORES,
            serializer=PydanticResultSerializer(model=BenchmarkEvaluationResult),
        ),
        PlatformJobResultRoute(
            name=JOB_RESULTS_ROW_SCORES,
            serializer=PydanticJSONLResultSerializer(model=RowScore),
        ),
        PlatformJobResultRoute(name=JOBS_RESULTS_ARTIFACTS, serializer=FileResultSerializer()),
    ],
)

# Rebase job routes from /jobs to / so we can include with /benchmark-jobs prefix.
# This avoids route collision with /benchmarks/{name} endpoints (e.g., a benchmark named "jobs").
_benchmark_jobs_router = APIRouter()
for route in _jobs_router.routes:
    if isinstance(route, APIRoute):
        # Remove /jobs prefix from path: '/jobs' -> '', '/jobs/{name}' -> '/{name}'
        new_path = route.path
        if new_path.startswith("/jobs"):
            new_path = new_path[5:]
        _benchmark_jobs_router.add_api_route(
            path=new_path,
            endpoint=route.endpoint,
            methods=route.methods,
            name=route.name,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            operation_id=route.operation_id,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            include_in_schema=route.include_in_schema,
            response_class=route.response_class,
            openapi_extra=route.openapi_extra,
        )

router.include_router(_benchmark_jobs_router, prefix="/v2/workspaces/{workspace}/benchmark-jobs")


# =============================================================================
# /v2/workspaces/{workspace}/benchmarks
# =============================================================================


@router.get(
    "/v2/workspaces/{workspace}/benchmarks",
    description="List all available evaluation benchmarks.",
    response_model=BenchmarksListResponse,
    tags=[API_TAG],
    response_model_exclude_none=True,
    openapi_extra={
        "parameters": [
            {
                "in": "query",
                "name": "filter",
                "style": "deepObject",
                "required": False,
                "explode": True,
                "schema": BenchmarksListFilter.model_json_schema(ref_template="#/components/schemas/{model}"),
                "description": (
                    "Filter benchmarks by name, description, dataset, project, and dates. "
                    "Supports JSON filter syntax with operators: "
                    "$eq, $like, $lt, $lte, $gt, $gte, $in, $nin, $and, $or, $not. "
                    "Also supports text filter syntax."
                ),
            },
        ]
    },
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid Request Body",
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Validation Error",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def list_benchmarks(
    workspace: str,
    request: Request,
    benchmarks_manager: BenchmarksManagerDep,
    parsed_filter: BenchmarksFilterDep,
    extended_response: bool = Query(default=False, description="Whether to return the extended benchmark."),
    page: int = Query(default=1, description="Page number."),
    page_size: int = Query(default=100, description="Page size."),
    sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"] = Query(
        default="-created_at",
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
        examples=["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"],
    ),
):
    """List all evaluation benchmarks with optional filtering, pagination, and sorting."""

    validate_list_query_params(request, {"extended_response"})
    _logger.info("Listing benchmarks", extra={"workspace": workspace})

    results = await benchmarks_manager.get_all(
        workspace=workspace,
        extended_response=extended_response,
        page=page,
        page_size=page_size,
        sort=sort,
        parsed_filter=parsed_filter,
    )

    return Page(
        data=results.data,
        pagination=PaginationData(**results.pagination.model_dump()),
        sort=sort,
        filter=parsed_filter.to_response(),
    )


@router.get(
    "/v2/workspaces/{workspace}/benchmarks/{name}",
    description="Get a specific evaluation benchmark by workspace and benchmark name.",
    response_model=Benchmark | ExtendedBenchmark | SystemBenchmark,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "Benchmark Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Validation Error",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def get_benchmark(
    workspace: str,
    name: str,
    benchmarks_manager: BenchmarksManagerDep,
    extended_response: bool = Query(default=False, description="Whether to return the extended benchmark."),
):
    """Get a specific evaluation benchmark by workspace and benchmark name."""
    _logger.info("Getting benchmark", extra={"workspace": workspace, "benchmark_name": name})

    try:
        benchmark = await benchmarks_manager.get_by_name(workspace, name, extended_response=extended_response)
    except BenchmarkRetrievalError as e:
        if e.error_code == "BENCHMARK_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail) from e
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail) from e

    return benchmark


@router.post(
    "/v2/workspaces/{workspace}/benchmarks",
    description=textwrap.dedent("""
        Create a new custom evaluation benchmark.

        Benchmarks can be reused across multiple evaluations. The benchmark type determines
        the evaluation method (currently only LLM-as-a-Judge is supported).
    """),
    status_code=status.HTTP_201_CREATED,
    response_model=Benchmark | ExtendedBenchmark,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid Request Body",
            "model": ErrorResponse,
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Operation Not Permitted",
            "model": ErrorResponse,
        },
        status.HTTP_409_CONFLICT: {
            "description": "Benchmark Already Exists",
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Validation Error",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def create_benchmark(
    workspace: str,
    benchmark: BenchmarkRequest,
    benchmarks_manager: BenchmarksManagerDep,
    sdk: SdkDep,
    extended_response: bool = Query(default=False, description="Whether to return the extended benchmark."),
):
    """Create a new evaluation benchmark."""
    if workspace == SYSTEM_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create benchmark in 'system' workspace reserved for system defined entities. "
            "Select another workspace for the benchmark.",
        )

    _logger.info("Creating benchmark", extra={"workspace": workspace, "benchmark_name": benchmark.name})

    try:
        return await benchmarks_manager.create(workspace, benchmark, sdk, extended_response=extended_response)
    except BenchmarkCreationError as e:
        _logger.warning("Error creating benchmark", extra={"detail": e.detail})
        if e.error_code == "METRIC_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail) from e
        if e.error_code == "BENCHMARK_ALREADY_EXISTS":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail) from e
        if e.error_code in {"INVALID_BENCHMARK", "INVALID_METRIC"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=e.detail) from e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except Exception as e:
        _logger.exception("Error creating benchmark")
        detail = str(e) or f"Benchmark creation failed: {type(e).__name__}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from e


@router.delete(
    "/v2/workspaces/{workspace}/benchmarks/{name}",
    description=textwrap.dedent("""
        Delete a custom evaluation benchmark. Predefined benchmarks cannot be deleted.
    """),
    response_model=DeleteResponse,
    tags=[API_TAG],
    responses={
        status.HTTP_200_OK: {
            "description": "Benchmark Deleted Successfully",
            "model": DeleteResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid Request Body",
            "model": ErrorResponse,
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Operation Not Permitted",
            "model": ErrorResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Benchmark Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Validation Error",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def delete_benchmark(workspace: str, name: str, benchmarks_manager: BenchmarksManagerDep):
    """Delete a custom evaluation benchmark."""
    if workspace == SYSTEM_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete benchmark in 'system' workspace reserved for system defined entities. "
            "Select another workspace for the benchmark.",
        )

    _logger.info("Deleting benchmark", extra={"workspace": workspace, "benchmark_name": name})

    try:
        delete_response: DeleteResponse = await benchmarks_manager.delete(workspace, name)
    except BenchmarkDeletionError as e:
        if e.error_code == "BENCHMARK_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail) from e
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail) from e

    return DeleteResponse(id=delete_response.id, message=delete_response.message, deleted_at=datetime.now())


# =============================================================================
# /v2/workspaces/{workspace}/benchmark-job-results
# =============================================================================


@router.get(
    "/v2/workspaces/{workspace}/benchmark-job-results",
    description="List stored evaluation results for benchmark jobs.",
    response_model=BenchmarkJobResultsListResponse,
    tags=[API_TAG],
    response_model_exclude_none=True,
    openapi_extra={
        "parameters": [
            {
                "in": "query",
                "name": "filter",
                "style": "deepObject",
                "required": False,
                "explode": True,
                "schema": BenchmarkJobResultsListFilter.model_json_schema(ref_template="#/components/schemas/{model}"),
                "description": (
                    "Filter benchmark job results by name, benchmark, metrics, dataset, model, and dates. "
                    "Supports JSON filter syntax with operators: "
                    "$eq, $like, $lt, $lte, $gt, $gte, $in, $nin, $and, $or, $not. "
                    "Also supports text filter syntax."
                ),
            },
        ]
    },
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Query Parameter Validation Error",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def list_benchmark_job_results(
    workspace: str,
    request: Request,
    benchmarks_manager: BenchmarksManagerDep,
    aggregate_fields: AggregateFieldsQuery,
    parsed_filter: BenchmarkJobResultsFilterDep,
    page: int = Query(default=1, description="Page number."),
    page_size: int = Query(default=100, description="Page size."),
    sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"] = Query(
        default="-created_at",
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
        examples=["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"],
    ),
):
    """List benchmark job results with optional filtering, pagination, and sorting."""

    validate_list_query_params(request, {"aggregate_fields"})
    _logger.info("Listing benchmark job results", extra={"workspace": workspace})

    # Convert list to frozenset (or None if empty to use defaults)
    fields = frozenset(aggregate_fields) if aggregate_fields else None

    return await benchmarks_manager.get_job_results(
        workspace=workspace,
        aggregate_fields=fields,
        page=page,
        page_size=page_size,
        sort=sort,
        parsed_filter=parsed_filter,
    )


@router.get(
    "/v2/workspaces/{workspace}/benchmark-job-results/{name}",
    description="Get a specific benchmark job result by workspace and job name.",
    response_model=BenchmarkJobResult,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_200_OK: {
            "description": "Benchmark Job Result Found",
            "model": BenchmarkJobResult,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Benchmark Job Result Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def get_benchmark_job_result(
    workspace: str, name: str, benchmarks_manager: BenchmarksManagerDep, aggregate_fields: AggregateFieldsQuery
):
    """Get a specific benchmark job result by workspace and job name."""
    _logger.info("Getting benchmark job result", extra={"workspace": workspace, "benchmark_job_result_name": name})

    # Convert list to frozenset (or None if empty to use defaults)
    fields = frozenset(aggregate_fields) if aggregate_fields else None

    try:
        return await benchmarks_manager.get_job_result(workspace, name, aggregate_fields=fields)
    except BenchmarkRetrievalError as e:
        if e.error_code == "BENCHMARK_JOB_RESULT_NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.detail) from e
        else:
            raise HTTPException(status_code=500, detail=e.detail) from e


@router.delete(
    "/v2/workspaces/{workspace}/benchmark-job-results/{name}",
    description="Delete an evaluation benchmark job result.",
    response_model=DeleteResponse,
    tags=[API_TAG],
    responses={
        status.HTTP_200_OK: {
            "description": "Benchmark Job Result Deleted Successfully",
            "model": DeleteResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Benchmark Job Result Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def delete_benchmark_job_result(workspace: str, name: str, benchmarks_manager: BenchmarksManagerDep):
    """Delete an evaluation benchmark job result."""
    _logger.info("Deleting benchmark job result", extra={"workspace": workspace, "benchmark_job_result_name": name})

    try:
        return await benchmarks_manager.delete_job_result(workspace, name)
    except BenchmarkDeletionError as e:
        if e.error_code == "BENCHMARK_JOB_RESULT_NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.detail)
        else:
            raise HTTPException(status_code=500, detail=e.detail)
