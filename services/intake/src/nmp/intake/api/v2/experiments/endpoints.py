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
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, NamedTuple, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nmp.common.api.common import Page, PaginationData
from nmp.common.api.filter import ComparisonOperation, FilterOperation, FilterOperator, LogicalOperation
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

ExperimentGroupSortField = Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"]

# The experiments list is sorted in the application layer (compute-on-read) so a single request can
# sort by a ClickHouse rollup metric, not just entity columns. `sort` is therefore a free string,
# validated against these: an entity column, run_count, or a `<metric>.<stat>` rollup path.
_ENTITY_SORT_FIELDS = frozenset({"name", "created_at", "updated_at", "pinned_at"})
_METRIC_STATS = frozenset({"sum", "mean", "median", "p90", "p95", "p99", "count"})
# Per-group experiment fetch bound for the in-memory merge. Groups are expected to hold at most
# hundreds; a query that selects more than this is rejected rather than sorted on a partial set — the
# trigger to denormalize metrics into an entity-store-sortable column instead.
_MAX_GROUP_EXPERIMENTS = 1000

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
    sort: ExperimentGroupSortField = Query(
        default="-created_at", description="Sort field; prefix with '-' for descending."
    ),
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
    responses = [ExperimentGroupResponse.from_entity(e) for e in result.data]
    counts = await _count_live_experiments_by_group(
        entity_client, workspace=workspace, group_ids=[g.id for g in result.data]
    )
    for response in responses:
        response.experiment_count = counts.get(response.id, 0)
    return Page(
        data=responses,
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
    response = ExperimentGroupResponse.from_entity(entity)
    response.experiment_count = await _count_live_experiments_in_group(
        entity_client, workspace=workspace, group_id=entity.id
    )
    return response


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
    response = ExperimentGroupResponse.from_entity(updated)
    response.experiment_count = await _count_live_experiments_in_group(
        entity_client, workspace=workspace, group_id=updated.id
    )
    return response


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
    responses={
        400: {"description": "Unsupported sort or filter field"},
        413: {"description": "Too many experiments selected to sort in one request"},
        503: {"description": "Telemetry store unavailable for a metric-based sort or filter"},
    },
    openapi_extra=generate_openapi_extra_params(
        filter_schema=ExperimentFilter,
        filter_description=(
            "Filter experiments by name, experiment_group_id, "
            "dataset_name, dataset_version, created_by, created_at, or updated_at. "
            "Pass is_deleted=true to return only soft-deleted experiments; omit to see only live ones. "
            "Pass is_pinned=true (or false) to filter by pinned state; omit to return both. "
            "Filter by a rollup metric with numeric range operators ($gte/$lte/$gt/$lt/$eq): "
            "filter[run_count][$gte]=5, filter[cost_usd.mean][$lte]=0.5, "
            "filter[latency_ms.p95][$lte]=1000, or filter[evaluators.<name>.mean][$gte]=0.8."
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
    sort: str = Query(
        default="-created_at",
        description=(
            "Field to sort by; prefix with '-' for descending. Sort by an experiment attribute "
            "(name, created_at, updated_at, pinned_at) or by an aggregate metric: run_count, "
            "cost_usd.<stat>, latency_ms.<stat>, or evaluators.<name>.<stat>, where <stat> is one of "
            "mean, median, p90, p95, p99, sum, count."
        ),
    ),
) -> Page[ExperimentResponse]:
    validate_list_query_params(request)
    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    _validate_sort_field(sort_field)
    _apply_is_deleted_filter(parsed)
    _apply_is_pinned_filter(parsed)
    # Rollup-metric predicates live in ClickHouse, not the entity store, so they can't be pushed to
    # Postgres. Split them out of the filter tree: only the entity predicates go to entity_client.list;
    # the metric ones are applied in memory after hydration. parsed (the full user filter) is left
    # intact so the response still echoes it.
    entity_operation, metric_predicates = _extract_metric_predicates(parsed.operation)
    # Compute-on-read: fetch the whole (entity-filtered) group, hydrate every rollup, then filter, sort,
    # and paginate in memory so a single request can sort/filter by a ClickHouse metric that lives
    # outside the entity store. Bounded to hundreds of experiments per group (see _MAX_GROUP_EXPERIMENTS).
    result = await entity_client.list(
        Experiment,
        workspace=workspace,
        filter_operation=entity_operation,
        page=1,
        page_size=_MAX_GROUP_EXPERIMENTS,
    )
    responses = [ExperimentResponse.from_entity(e) for e in result.data]
    total_selected = result.pagination.total_results
    if total_selected > _MAX_GROUP_EXPERIMENTS:
        # The whole filtered set is sorted in memory; anything past the fetch cap can't be sorted, so a
        # returned page would be silently incomplete. Fail loudly and tell the caller how to scope the
        # query instead (or denormalize rollup metrics for entity-store sorting once groups grow this big).
        logger.warning(
            "Experiment list selected %d experiments, over the %d-row in-memory sort cap; refusing "
            "to return a partially sorted result.",
            total_selected,
            _MAX_GROUP_EXPERIMENTS,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"This query selects {total_selected} experiments, exceeding the maximum of "
                f"{_MAX_GROUP_EXPERIMENTS} that can be sorted in one request. Narrow the result with a "
                "filter (e.g. experiment_group_id)."
            ),
        )
    hydrated = await _hydrate_rollups(workspace=workspace, responses=responses, rollup_repository=rollup_repository)
    # A metric-backed sort or filter is meaningless without rollups: if hydration was skipped (ClickHouse
    # disabled or down) every metric value would be unset, so a metric sort would silently collapse to
    # name order and a metric filter would drop everything. Reject the request instead of returning a
    # misleading 200. Entity-column sorts/filters still work and an empty group still hydrates fine.
    metric_sort = sort_field not in _ENTITY_SORT_FIELDS
    if not hydrated and (metric_sort or metric_predicates):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot sort or filter experiments by a rollup metric: the telemetry store is unavailable.",
        )
    if metric_predicates:
        responses = [r for r in responses if _matches_metric_predicates(r, metric_predicates)]
    ordered = _sort_experiments(responses, field=sort_field, descending=descending)
    start = (page - 1) * page_size
    page_items = ordered[start : start + page_size]
    return Page(
        data=page_items,
        pagination=make_pagination(
            page=page, page_size=page_size, current_page_size=len(page_items), total_results=len(ordered)
        ),
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
# Experiment. PUT may only edit group membership, source link, description, metadata.
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


@router.post(
    "/v2/workspaces/{workspace}/experiments/{name}/pin",
    response_model=ExperimentResponse,
    tags=[EXPERIMENTS_TAG],
    responses={404: {"description": "Experiment not found"}},
)
async def pin_experiment(
    workspace: str,
    name: str,
    entity_client: EntityClientDep,
    rollup_repository: ExperimentRollupRepositoryDep,
) -> ExperimentResponse:
    """Pin an experiment to the top of the list (workspace-shared).

    Re-pinning an already-pinned experiment refreshes ``pinned_at`` to the current timestamp,
    which is intentional (most-recently-pinned sorts first).
    """
    entity = await _get_or_404(
        entity_client,
        Experiment,
        workspace=workspace,
        name=name,
        label="Experiment",
    )
    _reject_if_deleted(entity, workspace=workspace, name=name, label="Experiment")
    entity.pinned_at = datetime.now(timezone.utc)
    updated = await entity_client.update(entity)
    response = ExperimentResponse.from_entity(updated)
    await _hydrate_rollups(workspace=workspace, responses=[response], rollup_repository=rollup_repository)
    return response


@router.delete(
    "/v2/workspaces/{workspace}/experiments/{name}/pin",
    response_model=ExperimentResponse,
    tags=[EXPERIMENTS_TAG],
    responses={404: {"description": "Experiment not found"}},
)
async def unpin_experiment(
    workspace: str,
    name: str,
    entity_client: EntityClientDep,
    rollup_repository: ExperimentRollupRepositoryDep,
) -> ExperimentResponse:
    """Unpin an experiment. Idempotent: unpinning an already-unpinned experiment is a no-op."""
    entity = await _get_or_404(
        entity_client,
        Experiment,
        workspace=workspace,
        name=name,
        label="Experiment",
    )
    _reject_if_deleted(entity, workspace=workspace, name=name, label="Experiment")
    entity.pinned_at = None
    updated = await entity_client.update(entity)
    response = ExperimentResponse.from_entity(updated)
    await _hydrate_rollups(workspace=workspace, responses=[response], rollup_repository=rollup_repository)
    return response


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


async def _count_live_experiments_in_group(entity_client: EntityClient, *, workspace: str, group_id: str) -> int:
    """Return the number of non-soft-deleted experiments in a single group.

    Fetches via ``list(page_size=1)`` so the response carries only ``pagination.total_results``.
    Used by single-group endpoints (GET, PUT). List endpoints should use the bulk variant.
    """
    result = await entity_client.list(
        Experiment,
        workspace=workspace,
        filter_operation=LogicalOperation(
            operator=FilterOperator.AND,
            operations=[
                ComparisonOperation(operator=FilterOperator.EQ, field="data.experiment_group_id", value=group_id),
                LogicalOperation(
                    operator=FilterOperator.NOT,
                    operations=[
                        ComparisonOperation(operator=FilterOperator.EQ, field="data.is_deleted", value=True),
                    ],
                ),
            ],
        ),
        page=1,
        page_size=1,
    )
    return result.pagination.total_results


async def _count_live_experiments_by_group(
    entity_client: EntityClient, *, workspace: str, group_ids: list[str]
) -> dict[str, int]:
    """Bulk-count non-soft-deleted experiments for many groups in one (paginated) query.

    Issues a single ``IN``-filter list against the entity store and tallies per group_id
    client-side. Replaces N parallel ``_count_live_experiments_in_group`` calls on the
    group-list endpoint so the request shape is 1-to-1 with the entity store rather than
    1-to-N (which is fragile under web-server concurrency).

    Returns a ``{group_id: count}`` map covering every requested group_id, with ``0`` for
    groups that have no live experiments.
    """
    counts: dict[str, int] = {group_id: 0 for group_id in group_ids}
    if not group_ids:
        return counts
    page = 1
    # Aligned with ``EntityClient.list``'s max — paginates when a workspace's total live
    # experiment count across the requested groups exceeds this.
    page_size = 1000
    filter_operation = LogicalOperation(
        operator=FilterOperator.AND,
        operations=[
            ComparisonOperation(operator=FilterOperator.IN, field="data.experiment_group_id", value=list(group_ids)),
            LogicalOperation(
                operator=FilterOperator.NOT,
                operations=[
                    ComparisonOperation(operator=FilterOperator.EQ, field="data.is_deleted", value=True),
                ],
            ),
        ],
    )
    while True:
        result = await entity_client.list(
            Experiment,
            workspace=workspace,
            filter_operation=filter_operation,
            page=page,
            page_size=page_size,
        )
        for experiment in result.data:
            counts[experiment.experiment_group_id] = counts.get(experiment.experiment_group_id, 0) + 1
        if page >= result.pagination.total_pages:
            break
        page += 1
    return counts


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


def _apply_is_pinned_filter(parsed: ParsedFilter) -> None:
    """Translate the user-facing ``is_pinned`` boolean into a clause on ``data.pinned_at``.

    The entity stores ``pinned_at: datetime | None``; "pinned" maps to "not null".

    - ``filter[is_pinned]=true``  → ``data.pinned_at IS NOT NULL`` (only pinned rows).
    - ``filter[is_pinned]=false`` → ``data.pinned_at IS NULL`` (only unpinned rows).
    - Omitted                     → no filter clause; both pinned and unpinned are returned.
    """
    raw_value = parsed.remove("is_pinned")
    if isinstance(raw_value, bool):
        want_pinned: bool | None = raw_value
    elif isinstance(raw_value, str):
        want_pinned = raw_value.strip().lower() in ("true", "1", "yes")
    else:
        want_pinned = None
    if want_pinned is None:
        return
    null_clause = ComparisonOperation(operator=FilterOperator.EQ, field="data.pinned_at", value=None)
    if want_pinned:
        parsed.and_with(LogicalOperation(operator=FilterOperator.NOT, operations=[null_clause]))
    else:
        parsed.and_with(null_clause)


# Metric heads whose dotted sub-paths address a ClickHouse rollup (not an entity column). Declared as
# self-mapping namespaces on ExperimentFilter so paths survive filter validation untranslated.
_METRIC_NAMESPACES = frozenset({"cost_usd", "latency_ms", "evaluators"})
_NUMERIC_FILTER_OPERATORS = frozenset(
    {FilterOperator.GTE, FilterOperator.LTE, FilterOperator.GT, FilterOperator.LT, FilterOperator.EQ}
)


class _MetricPredicate(NamedTuple):
    field: str
    operator: FilterOperator
    threshold: float


def _is_valid_metric_path(field: str) -> bool:
    """True if `field` is a rollup-metric path: run_count, <metric>.<stat>, or evaluators.<name>.<stat>."""
    if field == "run_count":
        return True
    head, _, rest = field.partition(".")
    if head in ("cost_usd", "latency_ms"):
        return rest in _METRIC_STATS
    if head == "evaluators":
        # Evaluator names can contain dots (e.g. "harbor.verifier"); the stat is the last segment.
        name, _, stat = rest.rpartition(".")
        return bool(name) and stat in _METRIC_STATS
    return False


def _validate_sort_field(field: str) -> None:
    """Reject a sort field that isn't an entity column or a known rollup-metric path."""
    if field in _ENTITY_SORT_FIELDS or _is_valid_metric_path(field):
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported sort field: {field}")


def _is_metric_field(field: str) -> bool:
    """True if `field` is *intended* as a rollup metric (by head), valid path or not.

    Looser than ``_is_valid_metric_path``: classifies e.g. ``cost_usd.bogus`` as a metric so it gets
    extracted and rejected with a 400 rather than forwarded to the entity store. Entity fields (already
    translated to ``data.*`` by the filter dep) never match.
    """
    return field == "run_count" or field.split(".", 1)[0] in _METRIC_NAMESPACES


def _operation_references_metric(operation: FilterOperation | None) -> bool:
    if isinstance(operation, ComparisonOperation):
        return _is_metric_field(operation.field)
    if isinstance(operation, LogicalOperation):
        return any(_operation_references_metric(child) for child in operation.operations)
    return False


def _validated_metric_predicate(operation: ComparisonOperation) -> _MetricPredicate:
    field = operation.field
    if not _is_valid_metric_path(field):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported metric filter field: {field}")
    if operation.operator not in _NUMERIC_FILTER_OPERATORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric filter '{field}' supports only numeric operators ($gte/$lte/$gt/$lt/$eq).",
        )
    try:
        threshold = float(operation.value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric filter '{field}' requires a numeric value, got {operation.value!r}.",
        ) from exc
    return _MetricPredicate(field=field, operator=operation.operator, threshold=threshold)


def _extract_metric_predicates(
    operation: FilterOperation | None,
) -> tuple[FilterOperation | None, list[_MetricPredicate]]:
    """Split rollup-metric comparisons out of the filter tree.

    Returns ``(entity_operation, metric_predicates)``: the entity operation is forwarded to the entity
    store, the metric predicates are applied in memory after hydration. Metric filters must be AND-ed
    (at any nesting depth) with entity filters; a metric field under OR/NOT raises 400, since we can't
    evaluate half a boolean tree in SQL and half in the application layer. Nested ANDs are flattened by
    recursion, so a metric comparison inside a sub-AND is accepted.
    """
    if operation is None:
        return None, []
    if isinstance(operation, ComparisonOperation):
        if _is_metric_field(operation.field):
            return None, [_validated_metric_predicate(operation)]
        return operation, []
    if isinstance(operation, LogicalOperation):
        if operation.operator != FilterOperator.AND:
            if _operation_references_metric(operation):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Metric filters can only be combined with AND, not OR/NOT.",
                )
            return operation, []
        entity_ops: list[FilterOperation] = []
        metric_predicates: list[_MetricPredicate] = []
        for child in operation.operations:
            # Recurse so metric comparisons nested inside sub-ANDs are extracted too (and OR/NOT
            # children that reference a metric still raise inside this call).
            child_entity, child_metrics = _extract_metric_predicates(child)
            if child_entity is not None:
                entity_ops.append(child_entity)
            metric_predicates.extend(child_metrics)
        if not entity_ops:
            return None, metric_predicates
        if len(entity_ops) == 1:
            return entity_ops[0], metric_predicates
        return LogicalOperation(operator=FilterOperator.AND, operations=entity_ops), metric_predicates
    return operation, []


def _matches_metric_predicates(response: ExperimentResponse, predicates: list[_MetricPredicate]) -> bool:
    """True if the response satisfies every metric predicate. A missing metric never matches."""
    for predicate in predicates:
        value = _experiment_sort_value(response, predicate.field)
        if value is None or not _compare_metric(value, predicate.operator, predicate.threshold):
            return False
    return True


def _compare_metric(value: float, operator: FilterOperator, threshold: float) -> bool:
    if operator == FilterOperator.GTE:
        return value >= threshold
    if operator == FilterOperator.LTE:
        return value <= threshold
    if operator == FilterOperator.GT:
        return value > threshold
    if operator == FilterOperator.LT:
        return value < threshold
    return value == threshold  # EQ


def _experiment_sort_value(response: ExperimentResponse, field: str) -> Any:
    """Value for `field` on a hydrated response, or None when the metric is absent (sorts last)."""
    if field in _ENTITY_SORT_FIELDS:
        return getattr(response, field)
    if field == "run_count":
        return response.run_count
    head, _, rest = field.partition(".")
    if head == "cost_usd":
        return getattr(response.cost_usd, rest, None) if response.cost_usd is not None else None
    if head == "latency_ms":
        return getattr(response.latency_ms, rest, None) if response.latency_ms is not None else None
    name, _, stat = rest.rpartition(".")  # head == "evaluators"
    score = (response.aggregate_scores or {}).get(name)
    return getattr(score, stat, None) if score is not None else None


def _sort_experiments(responses: list[ExperimentResponse], *, field: str, descending: bool) -> list[ExperimentResponse]:
    """Sort by an entity column or rollup metric; missing values sort last, ties broken by name."""
    by_name = sorted(responses, key=lambda r: r.name)  # deterministic tiebreak under the stable sort below
    valued = [(_experiment_sort_value(r, field), r) for r in by_name]
    present = [(value, r) for value, r in valued if value is not None]
    missing = [r for value, r in valued if value is None]
    present.sort(key=lambda pair: pair[0], reverse=descending)
    return [r for _, r in present] + missing


async def _hydrate_rollups(
    *,
    workspace: str,
    responses: list[ExperimentResponse],
    rollup_repository: ExperimentRollupRepository | None,
) -> bool:
    """Enrich responses with ClickHouse rollups in place.

    Returns True when hydration completed (including the no-op empty-list case) and False when it was
    skipped because the rollup store is unavailable (repository absent or query failed). Callers that
    sort by a rollup metric use the flag to reject the request rather than silently degrade; callers
    that only display metrics can ignore it.
    """
    if not responses:
        return True
    if rollup_repository is None:
        return False
    try:
        rollups = await rollup_repository.get_rollups(
            workspace=workspace, experiment_ids=[response.name for response in responses]
        )
    except Exception:
        logger.exception("Skipping experiment rollup hydration because ClickHouse is unavailable")
        return False
    for response in responses:
        rollup = rollups.get(response.name)
        if rollup is not None:
            _apply_rollup(response, rollup)
    return True


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
