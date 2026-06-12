# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Create, list, get, and delete endpoints for Experiments and ExperimentGroups.

Entity-store (Postgres) operations are wired directly onto ``EntityClient``,
following the inline pattern used by the core services. PUT updates only the
mutable fields; an Experiment's identity and the dataset/agent it ran against
are fixed. Rollup fields on read models are hydrated from ClickHouse.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Annotated, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nmp.common.api.common import Page, PaginationData
from nmp.common.api.filter import ComparisonOperation, FilterOperator, LogicalOperation
from nmp.common.api.parsed_filter import ParsedFilter, make_filter_dep
from nmp.common.api.utils import generate_openapi_extra_params
from nmp.common.entities.client import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.common.service.dependencies import get_entity_client
from nmp.intake.api.v2.experiments.schemas import (
    EvaluatorAggregate,
    ExperimentFilter,
    ExperimentGroupFilter,
    ExperimentGroupRequest,
    ExperimentGroupResponse,
    ExperimentRequest,
    ExperimentResponse,
    ExperimentSessionFilter,
    ExperimentSessionResponse,
)
from nmp.intake.entities.experiments import Experiment, ExperimentGroup
from nmp.intake.spans.api.dependencies import require_workspace_access, validate_list_query_params
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import SpanStatus
from nmp.intake.spans.experiment_rollup_repository import (
    ExperimentRollup,
    ExperimentRollupRepository,
    ScoreRollup,
)
from nmp.intake.spans.experiment_session_repository import ExperimentSessionRepository
from nmp.intake.spans.storage import make_pagination

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str) -> str:
    return value.replace("\r", "").replace("\n", "")


router = APIRouter(dependencies=[Depends(require_workspace_access)])

GROUPS_TAG = "Experiment Groups"
EXPERIMENTS_TAG = "Experiments"

SortField = Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"]
EntityT = TypeVar("EntityT", Experiment, ExperimentGroup)

EntityClientDep = Annotated[EntityClient, Depends(get_entity_client)]
ExperimentGroupFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(ExperimentGroupFilter))]
ExperimentFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(ExperimentFilter))]
ExperimentSessionFilterDep = Annotated[ParsedFilter, Depends(make_filter_dep(ExperimentSessionFilter))]


def _get_clickhouse_client(request: Request) -> ClickHouseSpanClient | None:
    service = getattr(request.app.state, "intake_service", None) or getattr(request.app.state, "service", None)
    if service is None:
        return None
    return getattr(service, "clickhouse_client", None)


def get_experiment_rollup_repository(request: Request) -> ExperimentRollupRepository | None:
    # Rollups are enrichment only. Experiment entity reads should continue when
    # ClickHouse is disabled or temporarily unavailable.
    client = _get_clickhouse_client(request)
    return ExperimentRollupRepository(client) if client is not None else None


ExperimentRollupRepositoryDep = Annotated[ExperimentRollupRepository | None, Depends(get_experiment_rollup_repository)]


def get_experiment_session_repository(request: Request) -> ExperimentSessionRepository | None:
    client = _get_clickhouse_client(request)
    return ExperimentSessionRepository(client) if client is not None else None


ExperimentSessionRepositoryDep = Annotated[
    ExperimentSessionRepository | None, Depends(get_experiment_session_repository)
]


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
    _apply_is_deleted_filter(parsed)
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
    entity = await _get_or_404(
        entity_client,
        ExperimentGroup,
        workspace=workspace,
        name=name,
        label="Experiment group",
    )
    _reject_if_deleted(entity, workspace=workspace, name=name, label="Experiment group")
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
    existing = await _get_or_404(
        entity_client,
        ExperimentGroup,
        workspace=workspace,
        name=name,
        label="Experiment group",
    )
    _reject_if_deleted(existing, workspace=workspace, name=name, label="Experiment group")
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
    # Soft delete: flip ``is_deleted`` and rename the row so the original name is free for reuse.
    # The unique index on (workspace, entity_type, name) doesn't read into the JSON data column,
    # so renaming on delete is what lets a new group/experiment claim the same name later.
    group = await _get_or_404(
        entity_client,
        ExperimentGroup,
        workspace=workspace,
        name=name,
        label="Experiment group",
    )
    _reject_if_deleted(group, workspace=workspace, name=name, label="Experiment group")

    # Cascade is sequential — one update per child. Linear in group size, fine for now. If
    # groups routinely hold more than a few hundred experiments, add a bulk update endpoint on
    # the entity store rather than parallelizing here (gather hides partial-failure state
    # without removing the per-row API contract).
    #
    # Each ``_soft_delete`` renames the row and flips ``is_deleted=True``, which drops it out of
    # the live filter — so re-fetching page 1 keeps returning the next batch until nothing is
    # left. No fixed cap on group size.
    #
    # ``data.experiment_group_id`` is the entity-store field name; the URL filter dep auto-
    # prefixes ``data.`` but manually-constructed ComparisonOperations don't get that translation.
    live_children_filter = LogicalOperation(
        operator=FilterOperator.AND,
        operations=[
            ComparisonOperation(operator=FilterOperator.EQ, field="data.experiment_group_id", value=group.id),
            LogicalOperation(
                operator=FilterOperator.NOT,
                operations=[
                    ComparisonOperation(operator=FilterOperator.EQ, field="data.is_deleted", value=True),
                ],
            ),
        ],
    )
    while True:
        page = await entity_client.list(
            Experiment,
            workspace=workspace,
            filter_operation=live_children_filter,
            page=1,
            page_size=100,
        )
        if not page.data:
            break
        for child in page.data:
            await _soft_delete(entity_client, child)
    await _soft_delete(entity_client, group)


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
    await _validate_group_exists(entity_client, group_id=body.experiment_group_id)
    entity = Experiment(
        workspace=workspace,
        name=body.name,
        experiment_group_id=body.experiment_group_id,
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
        filter_description=(
            "Filter experiments by name, experiment_group_id, "
            "dataset_name, dataset_version, created_by, created_at, or updated_at. "
            "Pass is_deleted=true to return only soft-deleted experiments; omit to see only live ones."
        ),
    ),
)
async def list_experiments(
    workspace: str,
    request: Request,
    entity_client: EntityClientDep,
    rollup_repository: ExperimentRollupRepositoryDep,
    parsed: ExperimentFilterDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size."),
    sort: SortField = Query(default="-created_at", description="Sort field; prefix with '-' for descending."),
) -> Page[ExperimentResponse]:
    validate_list_query_params(request)
    _apply_is_deleted_filter(parsed)
    result = await entity_client.list(
        Experiment,
        workspace=workspace,
        filter_operation=parsed.operation,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    responses = [ExperimentResponse.from_entity(e) for e in result.data]
    await _hydrate_rollups(workspace=workspace, responses=responses, rollup_repository=rollup_repository)
    return Page(
        data=responses,
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
    rollup_repository: ExperimentRollupRepositoryDep,
) -> ExperimentResponse:
    entity = await _get_or_404(
        entity_client,
        Experiment,
        workspace=workspace,
        name=name,
        label="Experiment",
    )
    _reject_if_deleted(entity, workspace=workspace, name=name, label="Experiment")
    response = ExperimentResponse.from_entity(entity)
    await _hydrate_rollups(workspace=workspace, responses=[response], rollup_repository=rollup_repository)
    return response


# Identity and the dataset it was run against are fixed for the life of an
# Experiment (see the ingest invariants); changing them means it's a different
# Experiment. PUT may only edit group membership, source link, summary, description, metadata.
_IMMUTABLE_EXPERIMENT_FIELDS = ("name", "dataset_name", "dataset_version")


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
    rollup_repository: ExperimentRollupRepositoryDep,
) -> ExperimentResponse:
    existing = await _get_or_404(
        entity_client,
        Experiment,
        workspace=workspace,
        name=name,
        label="Experiment",
    )
    _reject_if_deleted(existing, workspace=workspace, name=name, label="Experiment")
    if body.experiment_group_id != existing.experiment_group_id:
        await _validate_group_exists(entity_client, group_id=body.experiment_group_id)

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
    response = ExperimentResponse.from_entity(updated)
    await _hydrate_rollups(workspace=workspace, responses=[response], rollup_repository=rollup_repository)
    return response


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
    entity = await _get_or_404(
        entity_client,
        Experiment,
        workspace=workspace,
        name=name,
        label="Experiment",
    )
    _reject_if_deleted(entity, workspace=workspace, name=name, label="Experiment")
    await _soft_delete(entity_client, entity)


@router.get(
    "/v2/workspaces/{workspace}/experiments/{name}/sessions",
    response_model=Page[ExperimentSessionResponse],
    tags=[EXPERIMENTS_TAG],
    responses={
        404: {"description": "Experiment not found"},
        503: {"description": "ClickHouse unavailable"},
    },
    openapi_extra=generate_openapi_extra_params(
        filter_schema=ExperimentSessionFilter,
        filter_description="Filter sessions by test_case_id and status.",
    ),
)
async def list_experiment_sessions(
    workspace: str,
    name: str,
    request: Request,
    entity_client: EntityClientDep,
    session_repository: ExperimentSessionRepositoryDep,
    parsed: ExperimentSessionFilterDep,
    page: int = Query(default=1, ge=1, description="Page number."),
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size."),
) -> Page[ExperimentSessionResponse]:
    validate_list_query_params(request)
    experiment = await _get_or_404(
        entity_client,
        Experiment,
        workspace=workspace,
        name=name,
        label="Experiment",
    )
    _reject_if_deleted(experiment, workspace=workspace, name=name, label="Experiment")
    if session_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ClickHouse is unavailable; per-session reads require telemetry storage.",
        )
    test_case_id: str | None = parsed.extract("test_case_id")
    status_raw: str | None = parsed.extract("status")
    try:
        status_filter = SpanStatus(status_raw) if status_raw is not None else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{status_raw}'. Valid values: {[s.value for s in SpanStatus]}",
        )
    try:
        result = await session_repository.list_sessions(
            workspace=workspace,
            experiment_name=name,
            status=status_filter,
            test_case_id=test_case_id,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        # Sessions are the response payload (not enrichment), so we can't silently degrade like
        # _hydrate_rollups does. Convert backend failures (ClickHouse connection drop, query
        # timeout, etc.) to a deterministic 503 instead of letting them bubble as 500s.
        logger.exception(
            "Per-session read failed for workspace=%s experiment=%s",
            _sanitize_for_log(workspace),
            _sanitize_for_log(name),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telemetry store unavailable.",
        ) from exc
    data = [ExperimentSessionResponse.from_row(row) for row in result.rows]
    return Page(
        data=data,
        pagination=make_pagination(
            page=page,
            page_size=page_size,
            current_page_size=len(data),
            total_results=result.total,
        ),
        filter=parsed.to_response(),
    )


async def _get_or_404(
    entity_client: EntityClient,
    entity_type: type[EntityT],
    *,
    workspace: str,
    name: str,
    label: str,
) -> EntityT:
    try:
        return await entity_client.get(entity_type, name=name, workspace=workspace)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} '{workspace}/{name}' not found.",
        ) from e


def _reject_if_deleted(
    entity: Experiment | ExperimentGroup,
    *,
    workspace: str,
    name: str,
    label: str,
) -> None:
    """Treat soft-deleted entities as 404 for callers that didn't explicitly opt in."""
    if entity.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} '{workspace}/{name}' not found.",
        )


_DELETED_MARKER = "-deleted-"
_DELETED_RAND_BYTES = 3  # 6 lowercase hex chars; combined with millis is enough to avoid collisions.
_NAME_MAX_LEN = 63  # matches entity-store NAME_PATTERN length cap.


def _deleted_name(original: str) -> str:
    """Mangle a soft-deleted entity's name so the original is free for reuse.

    The DB unique index on (workspace, entity_type, name) doesn't see into the JSON
    ``data`` column, so the row needs a different ``name`` after soft-delete. The
    suffix is lowercase-only to satisfy NAME_PATTERN (``[a-z0-9\\-@.+_]``).
    """
    # Base36 of unix milliseconds is ~8 chars today and sortable; add 6 hex chars of
    # randomness so concurrent deletes can't collide within the same millisecond.
    ts = _to_base36(int(time.time() * 1000))
    rand = secrets.token_hex(_DELETED_RAND_BYTES)
    suffix = f"{_DELETED_MARKER}{ts}{rand}"
    head_budget = _NAME_MAX_LEN - len(suffix)
    head = original[:head_budget].rstrip("-") if len(original) > head_budget else original
    return f"{head}{suffix}"


def _to_base36(value: int) -> str:
    if value == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []
    while value:
        value, rem = divmod(value, 36)
        out.append(digits[rem])
    return "".join(reversed(out))


async def _soft_delete(entity_client: EntityClient, entity: Experiment | ExperimentGroup) -> None:
    """Flip ``is_deleted`` and rename the entity in a single update."""
    original_name = entity.name
    entity.is_deleted = True
    entity.name = _deleted_name(original_name)
    await entity_client.update(entity, original_name=original_name)


async def _validate_group_exists(entity_client: EntityClient, *, group_id: str) -> None:
    """Reject the request with 400 if the referenced ExperimentGroup doesn't exist or is deleted."""
    try:
        group = await entity_client.get_by_id(ExperimentGroup, entity_id=group_id)
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"ExperimentGroup '{group_id}' must be created before an Experiment can reference it."),
        ) from e
    if group.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ExperimentGroup '{group_id}' has been deleted and can no longer accept new Experiments.",
        )


def _apply_is_deleted_filter(parsed: ParsedFilter) -> None:
    """Append an ``is_deleted`` clause so list endpoints hide soft-deleted rows by default.

    If the caller passes ``filter[is_deleted]=true``, only soft-deleted rows are returned.
    Anything else (no filter, or ``filter[is_deleted]=false``) returns only live rows.
    """
    # Bracket-style filters arrive as strings (``filter[is_deleted]=true``); JSON-style filters
    # arrive as booleans. Normalize both before deciding which branch to take.
    raw_value = parsed.remove("is_deleted")
    if isinstance(raw_value, bool):
        want_deleted = raw_value
    elif isinstance(raw_value, str):
        want_deleted = raw_value.strip().lower() in ("true", "1", "yes")
    else:
        want_deleted = False
    if want_deleted:
        parsed.and_with(
            ComparisonOperation(operator=FilterOperator.EQ, field="data.is_deleted", value=True),
        )
        return
    parsed.and_with(
        LogicalOperation(
            operator=FilterOperator.NOT,
            operations=[
                ComparisonOperation(operator=FilterOperator.EQ, field="data.is_deleted", value=True),
            ],
        ),
    )


async def _hydrate_rollups(
    *,
    workspace: str,
    responses: list[ExperimentResponse],
    rollup_repository: ExperimentRollupRepository | None,
) -> None:
    if rollup_repository is None or not responses:
        return
    try:
        rollups = await rollup_repository.get_rollups(
            workspace=workspace, experiment_ids=[response.name for response in responses]
        )
    except Exception:
        logger.exception("Skipping experiment rollup hydration because ClickHouse is unavailable")
        return
    for response in responses:
        rollup = rollups.get(response.name)
        if rollup is not None:
            _apply_rollup(response, rollup)


def _apply_rollup(response: ExperimentResponse, rollup: ExperimentRollup) -> None:
    response.evaluator_names = rollup.evaluator_names
    response.model_names = rollup.model_names
    response.agent_names = rollup.agent_names
    response.agent_versions = rollup.agent_versions
    response.aggregate_scores = {name: _aggregate(score) for name, score in rollup.evaluator_scores.items()} or None
    response.run_count = rollup.run_count
    response.cost_usd = _aggregate(rollup.cost_usd) if rollup.cost_usd is not None else None
    response.latency_ms = _aggregate(rollup.latency_ms) if rollup.latency_ms is not None else None


def _aggregate(rollup: ScoreRollup) -> EvaluatorAggregate:
    return EvaluatorAggregate(
        sum=rollup.sum,
        mean=rollup.mean,
        median=rollup.median,
        p90=rollup.p90,
        p95=rollup.p95,
        p99=rollup.p99,
        count=rollup.count,
    )
