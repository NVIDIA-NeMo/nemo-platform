# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import textwrap
from typing import Annotated, Literal

import nmp.evaluator.app.values as app
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.routing import APIRoute
from nemo_evaluator_sdk.values import AggregatedMetricResult, RowScore
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
from nmp.common.api.common import DeleteResponse
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.entities import SYSTEM_WORKSPACE
from nmp.common.service.dependencies import get_entity_client, get_sdk_client
from nmp.evaluator.api.v2.common.query_params import AggregateFieldsQuery, validate_list_query_params
from nmp.evaluator.api.v2.common.schemas import ErrorResponse
from nmp.evaluator.api.v2.metrics.manager import (
    MetricDeletionError,
    MetricEvaluationError,
    MetricResolutionError,
    MetricRetrievalError,
    MetricsManager,
)
from nmp.evaluator.api.v2.metrics.schemas.evaluation import (
    MetricEvaluationRequest,
    MetricEvaluationResponse,
)
from nmp.evaluator.api.v2.metrics.schemas.jobs import (
    MetricJob,
)
from nmp.evaluator.api.v2.metrics.schemas.metrics import Metric
from nmp.evaluator.api.v2.metrics.schemas.metrics_resp import (
    MetricJobResult,
    MetricJobResultsListFilter,
    MetricJobResultsListResponse,
    MetricResponse,
    MetricsListFilter,
    MetricsListResponse,
)
from nmp.evaluator.app.jobs.constants import (
    JOB_RESULTS_AGGREGATE_SCORES,
    JOB_RESULTS_ROW_SCORES,
    JOBS_RESULTS_ARTIFACTS,
)

_logger = logging.getLogger(__name__)


API_TAG = "Evaluator"


router = APIRouter()


def get_metrics_manager(entity_client: Annotated[EntityClient, Depends(get_entity_client)]) -> MetricsManager:
    return MetricsManager(entity_client)


MetricsManagerDep = Annotated[MetricsManager, Depends(get_metrics_manager)]


# =============================================================================
# /v2/workspaces/{workspace}/metric-jobs
# =============================================================================


async def platform_job_config_compiler(
    workspace: str,
    original_spec: MetricJob,
    transformed_spec: MetricJob,
    entity_client: EntityClient,
    job_name: str | None,
    sdk: AsyncNeMoPlatform,
) -> PlatformJobSpec:
    """Compile a metric job spec to a platform job spec.

    This function provides exception mapping for the manager's compile_job method.

    Args:
        workspace: The workspace for this job.
        original_spec: The user-provided input specification.
        transformed_spec: The spec after applying the input-to-output transformer.
            Since no transformer is configured for metrics, original_spec
            and transformed_spec are identical (both MetricJob).
        entity_client: Entity client for lookups.
        job_name: The resolved job name (user-provided or auto-generated).
        sdk: SDK instance for accessing secrets with user context.
    """
    if isinstance(transformed_spec.metric, app.SystemMetric):
        # SystemMetric is needed for job response but job types represent input+response
        # We return 422 invalid payload when request contains inline system metrics until supported.
        err_msg = f"Unsupported job with custom system metric. Use metric reference instead 'system/<metric-name>': {transformed_spec.metric}"
        raise HTTPException(status_code=422, detail=err_msg)

    metrics_manager = get_metrics_manager(entity_client)

    try:
        return await metrics_manager.compile_job(workspace, transformed_spec, sdk=sdk)
    except MetricRetrievalError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    except MetricResolutionError as e:
        raise HTTPException(status_code=403, detail=e.detail) from e
    except (KeyError, ValueError, AssertionError, RuntimeError) as e:
        detail = str(e) or f"Job compilation failed: {type(e).__name__}"
        raise HTTPException(status_code=422, detail=detail) from e


_jobs_router = job_route_factory(
    # Use distinct job sources to prevent mixing incompatible job specs when listing.
    # (MetricEvaluation and BenchmarkEvaluation jobs have different spec schemas.)
    service_name="evaluator-metrics",
    job_type="MetricEvaluation",
    job_input=MetricJob,
    platform_job_config_compiler=platform_job_config_compiler,
    job_result_routes=[
        PlatformJobResultRoute(
            name=JOB_RESULTS_AGGREGATE_SCORES,
            serializer=PydanticResultSerializer(model=AggregatedMetricResult),
        ),
        PlatformJobResultRoute(
            name=JOB_RESULTS_ROW_SCORES,
            serializer=PydanticJSONLResultSerializer(model=RowScore),
        ),
        PlatformJobResultRoute(name=JOBS_RESULTS_ARTIFACTS, serializer=FileResultSerializer()),
    ],
)

# Rebase job routes from /jobs to / so we can include with /metric-jobs prefix.
# This avoids route collision with /metrics/{name} endpoints.
_metric_jobs_router = APIRouter()
for route in _jobs_router.routes:
    if isinstance(route, APIRoute):
        # Remove /jobs prefix from path: '/jobs' -> '', '/jobs/{name}' -> '/{name}'
        new_path = route.path
        if new_path.startswith("/jobs"):
            new_path = new_path[5:]
        _metric_jobs_router.add_api_route(
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

# TODO: There are no endpoints to list/filter job results
# We'll need to call list-jobs, and then for each job, call get-job-results
# Until then, these endpoints will not be available:
# GET /metrics/{namespace}/{name}/jobs/results # all results for a metric
# GET /metrics/jobs/results # all results for all metric jobs

router.include_router(_metric_jobs_router, prefix="/v2/workspaces/{workspace}/metric-jobs")


# =============================================================================
# /v2/workspaces/{workspace}/metrics
# =============================================================================


@router.get(
    "/v2/workspaces/{workspace}/metrics",
    description="List evaluation metrics.",
    response_model=MetricsListResponse,
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
                "schema": MetricsListFilter.model_json_schema(ref_template="#/components/schemas/{model}"),
                "description": (
                    "Filter metrics by name, description, type, project, and dates. "
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
async def list_metrics(
    workspace: str,
    request: Request,
    metrics_manager: MetricsManagerDep,
    page: int = Query(default=1, description="Page number."),
    page_size: int = Query(default=100, description="Page size."),
    sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"] = Query(
        default="-created_at",
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
        examples=["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"],
    ),
    parsed_filter: ParsedFilter = Depends(make_filter_dep(MetricsListFilter)),
):
    """List evaluation metrics with optional filtering, pagination, and sorting."""

    validate_list_query_params(request)
    _logger.info("Listing metrics", extra={"workspace": workspace})

    return await metrics_manager.get_all(
        workspace=workspace,
        page=page,
        page_size=page_size,
        sort=sort,
        parsed_filter=parsed_filter,
    )


@router.get(
    "/v2/workspaces/{workspace}/metrics/{name}",
    description="Get a specific evaluation metric by workspace and metric name.",
    response_model=MetricResponse,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_200_OK: {
            "description": "Metric Found",
            "model": MetricResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Metric Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def get_metric(workspace: str, name: str, metrics_manager: MetricsManagerDep):
    """Get a specific evaluation metric by workspace and metric name."""
    _logger.info("Getting metric", extra={"workspace": workspace, "metric_name": name})

    try:
        return await metrics_manager.get_by_name(workspace, name)
    except MetricRetrievalError as e:
        if e.error_code == "METRIC_NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.detail) from e
        else:
            raise HTTPException(status_code=500, detail=e.detail) from e


@router.post(
    "/v2/workspaces/{workspace}/metrics/{name}",
    description=textwrap.dedent("""
        Create a new custom evaluation metric.

        Metrics can be reused across multiple evaluations. The metric type determines
        the evaluation method (currently only LLM-as-a-Judge is supported).
    """),
    response_model=MetricResponse,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Metric Created Successfully",
            "model": MetricResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid Request Body",
            "model": ErrorResponse,
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Not Authorized to Create Metric.",
            "model": ErrorResponse,
        },
        status.HTTP_409_CONFLICT: {
            "description": "Metric Already Exists",
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
async def create_metric(
    workspace: str,
    name: str,
    metric_request: Metric,
    metrics_manager: MetricsManagerDep,
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
):
    """Create a new evaluation metric."""
    if workspace == SYSTEM_WORKSPACE:
        raise HTTPException(
            status_code=403,
            detail="Cannot create metric in 'system' workspace reserved for system defined entities. Select another workspace for the metric.",
        )

    _logger.info("Creating metric", extra={"workspace": workspace, "metric_name": name})
    return await metrics_manager.create_from_request(name=name, workspace=workspace, request=metric_request, sdk=sdk)


@router.delete(
    "/v2/workspaces/{workspace}/metrics/{name}",
    description=textwrap.dedent("""
        Delete a custom evaluation metric. Predefined metrics cannot be deleted.
    """),
    response_model=DeleteResponse,
    tags=[API_TAG],
    responses={
        status.HTTP_200_OK: {
            "description": "Metric Deleted Successfully",
            "model": DeleteResponse,
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Not Authorized to Delete Metric.",
            "model": ErrorResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Metric Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def delete_metric(workspace: str, name: str, metrics_manager: MetricsManagerDep):
    """Delete a custom evaluation metric."""
    if workspace == SYSTEM_WORKSPACE:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete metric in 'system' workspace reserved for system defined entities. Select another workspace for the metric.",
        )

    _logger.info("Deleting metric", extra={"workspace": workspace, "metric_name": name})

    try:
        return await metrics_manager.delete(workspace, name)
    except MetricDeletionError as e:
        if e.error_code == "METRIC_NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.detail)
        else:
            raise HTTPException(status_code=500, detail=e.detail)


# =============================================================================
# /v2/workspaces/{workspace}/metric-job-results
# =============================================================================


@router.get(
    "/v2/workspaces/{workspace}/metric-job-results",
    description="List stored evaluation results for metric jobs.",
    response_model=MetricJobResultsListResponse,
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
                "schema": MetricJobResultsListFilter.model_json_schema(ref_template="#/components/schemas/{model}"),
                "description": (
                    "Filter metric job results by name, metric, dataset, model, and dates. "
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
async def list_metric_job_results(
    workspace: str,
    request: Request,
    metrics_manager: MetricsManagerDep,
    aggregate_fields: AggregateFieldsQuery,
    page: int = Query(default=1, description="Page number."),
    page_size: int = Query(default=100, description="Page size."),
    sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"] = Query(
        default="-created_at",
        description="The field to sort by. To sort in decreasing order, use `-` in front of the field name.",
        examples=["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"],
    ),
    parsed_filter: ParsedFilter = Depends(make_filter_dep(MetricJobResultsListFilter)),
):
    """List metric job results with optional filtering, pagination, and sorting."""

    validate_list_query_params(request)
    _logger.info("Listing metric job results", extra={"workspace": workspace})

    # Convert list to frozenset (or None if empty to use defaults)
    fields = frozenset(aggregate_fields) if aggregate_fields else None

    return await metrics_manager.get_job_results(
        workspace=workspace,
        aggregate_fields=fields,
        page=page,
        page_size=page_size,
        sort=sort,
        parsed_filter=parsed_filter,
    )


@router.get(
    "/v2/workspaces/{workspace}/metric-job-results/{name}",
    description="Get a specific metric job result by workspace and job name.",
    response_model=MetricJobResult,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_200_OK: {
            "description": "Metric Job Result Found",
            "model": MetricJobResult,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Metric Job Result Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def get_metric_job_result(
    workspace: str, name: str, metrics_manager: MetricsManagerDep, aggregate_fields: AggregateFieldsQuery
):
    """Get a specific metric job result by workspace and job name."""
    _logger.info("Getting metric job result", extra={"workspace": workspace, "metric_job_result_name": name})

    # Convert list to frozenset (or None if empty to use defaults)
    fields = frozenset(aggregate_fields) if aggregate_fields else None

    try:
        return await metrics_manager.get_job_result(workspace, name, aggregate_fields=fields)
    except MetricRetrievalError as e:
        if e.error_code == "METRIC_JOB_RESULT_NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.detail) from e
        else:
            raise HTTPException(status_code=500, detail=e.detail) from e


@router.delete(
    "/v2/workspaces/{workspace}/metric-job-results/{name}",
    description="Delete an evaluation metric job result.",
    response_model=DeleteResponse,
    tags=[API_TAG],
    responses={
        status.HTTP_200_OK: {
            "description": "Metric Job Result Deleted Successfully",
            "model": DeleteResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Metric Job Result Not Found",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error",
            "model": ErrorResponse,
        },
    },
)
async def delete_metric_job_result(workspace: str, name: str, metrics_manager: MetricsManagerDep):
    """Delete an evaluation metric job result."""
    _logger.info("Deleting metric job result", extra={"workspace": workspace, "metric_job_result_name": name})

    try:
        return await metrics_manager.delete_job_result(workspace, name)
    except MetricDeletionError as e:
        if e.error_code == "METRIC_JOB_RESULT_NOT_FOUND":
            raise HTTPException(status_code=404, detail=e.detail)
        else:
            raise HTTPException(status_code=500, detail=e.detail)


# =============================================================================
# /v2/workspaces/{workspace}/metric-evaluate
# =============================================================================


# NOTE: This endpoint accepts the metric in the request body (URN or inline definition),
# following the pattern of /live. If needed, we could add a convenience endpoint:
#   POST /v2/workspaces/{workspace}/metrics/{name}/evaluate
# That would only accept samples in the body and resolve the metric from the path.
# For now, this single endpoint covers both stored and inline metric evaluation.
#
# TODO: Add query parameter to control expanding/collapsing properties like `metric` to their URN value.
@router.post(
    "/v2/workspaces/{workspace}/metric-evaluate",
    description=textwrap.dedent("""
        Run a synchronous metric evaluation on a dataset.

        This endpoint evaluates the given dataset using the specified metric and returns
        results immediately. Use this for quick, interactive evaluations with small datasets
        (up to 10 rows). For larger evaluations, use the async job-based evaluation endpoints.

        The metric can be specified either as a URN reference to a stored metric
        (e.g., "workspace/metric_name") or as an inline metric definition.

        The dataset must be provided inline with rows.

        **Aggregate Score Fields:**
        The `name` and `count` fields are always included in aggregate scores.
        By default, additional fields returned are: nan_count, sum, mean, min, max.
        Use the `aggregate_fields` query parameter to customize which optional fields
        are included (e.g., std_dev, variance, percentiles, histogram, rubric_distribution, mode_category).
    """),
    response_model=MetricEvaluationResponse,
    tags=[API_TAG],
    response_model_exclude_none=True,
    responses={
        status.HTTP_200_OK: {
            "description": "Evaluation Completed Successfully",
            "model": MetricEvaluationResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid Request Body",
            "model": ErrorResponse,
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Metric Not Found",
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
async def evaluate_metric(
    workspace: str,
    request: MetricEvaluationRequest,
    metrics_manager: MetricsManagerDep,
    aggregate_fields: AggregateFieldsQuery,
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
):
    """Run a metric evaluation on a dataset."""
    # Convert list to frozenset (or None if empty to use defaults)
    fields = frozenset(aggregate_fields) if aggregate_fields else None

    try:
        return await metrics_manager.evaluate(
            workspace=workspace,
            metric_ref=request.metric,
            dataset=request.dataset,
            sdk=sdk,
            aggregate_fields=fields,
        )
    except MetricRetrievalError as e:
        raise HTTPException(status_code=404, detail=e.detail) from e
    except MetricResolutionError as e:
        raise HTTPException(status_code=400, detail=e.detail) from e
    except MetricEvaluationError as e:
        raise HTTPException(status_code=500, detail=e.detail) from e
