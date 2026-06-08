# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Factory that wires up standard /versions sub-routes for any versioned entity type.

Usage
-----
Create the versioning router once per entity type and include it in the main router:

    _versions = make_versioning_router(
        parent_entity_type="prompt",
        version_entity_type="prompt_version",
        resource_path="prompts",
        version_schema=PromptVersion,
        version_create_schema=PromptVersionCreate,
        build_version_data=_build_prompt_version_data,
        to_version_response=_entity_to_prompt_version,
        api_tag="Prompts",
    )
    router.include_router(_versions)

The factory produces three routes:
  POST   /v2/workspaces/{workspace}/{resource_path}/{name}/versions
  GET    /v2/workspaces/{workspace}/{resource_path}/{name}/versions
  GET    /v2/workspaces/{workspace}/{resource_path}/{name}/versions/{version_number}

Version numbering
-----------------
Version numbers are sequential starting at 1.  The parent entity's data blob
must carry ``version_count`` (int) and ``current_version_name`` (str).  Both
are updated atomically alongside the new child entity in the same transaction.
Concurrent creation is protected by ``expected_db_version`` (optimistic lock).
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from nemo_platform_plugin.filter_ops import ComparisonOperation, FilterOperator, LogicalOperation
from nmp.common.api.common import Page, PaginationData
from nmp.core.entities.api.dependencies import EntityRepository
from nmp.core.entities.app.repository.exceptions import EntityAlreadyExistsError, EntityVersionConflictError
from nmp.core.entities.entities import Entity
from pydantic import BaseModel


def make_versioning_router(
    parent_entity_type: str,
    version_entity_type: str,
    resource_path: str,
    version_schema: type[BaseModel],
    version_create_schema: type[BaseModel],
    build_version_data: Callable[[Any, int], dict],
    to_version_response: Callable[[Entity, Entity], Any],
    api_tag: str,
) -> APIRouter:
    """Return a router with the three standard version sub-routes."""

    router = APIRouter()
    base = f"/v2/workspaces/{{workspace}}/{resource_path}/{{name}}"

    async def _get_parent_or_404(repository: EntityRepository, workspace: str, name: str) -> Entity:
        entity = await repository.get_entity_by_name(
            workspace=workspace,
            entity_type=parent_entity_type,
            name=name,
        )
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{name}' not found in workspace '{workspace}'",
            )
        return entity

    # ------------------------------------------------------------------
    # POST /versions — create a new version
    # ------------------------------------------------------------------

    async def create_version(
        workspace: str,
        name: str,
        version_in,  # annotated below so FastAPI sees the concrete schema
        repository: EntityRepository,
    ):
        parent = await _get_parent_or_404(repository, workspace, name)
        next_number: int = parent.data.get("version_count", 0) + 1
        version_name = f"{name}-v{next_number}"
        version_data = build_version_data(version_in, next_number)

        try:
            async with repository.transaction() as session:
                version_entity = await repository.create_entity(
                    workspace=workspace,
                    entity_type=version_entity_type,
                    name=version_name,
                    data=version_data,
                    parent=parent.id,
                    session=session,
                )
                updated_parent_data = dict(parent.data)
                updated_parent_data["version_count"] = next_number
                updated_parent_data["current_version_name"] = version_name
                parent = await repository.update_entity_by_name(
                    workspace=workspace,
                    entity_type=parent_entity_type,
                    name=name,
                    data=updated_parent_data,
                    expected_db_version=parent.db_version,
                    session=session,
                )
            return to_version_response(version_entity, parent)
        # Both failure modes are losers of a concurrent create race for the same
        # next version number: the parent's optimistic lock (db_version) or the
        # child's unique (parent, name) constraint. Either way, retry resolves it.
        except (EntityVersionConflictError, EntityAlreadyExistsError) as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another version was created concurrently. Please retry.",
            ) from e

    create_version.__annotations__["version_in"] = version_create_schema
    create_version.__annotations__["return"] = version_schema

    router.post(
        f"{base}/versions",
        response_model=version_schema,
        tags=[api_tag],
        status_code=201,
        summary=f"Create a new {parent_entity_type} version",
    )(create_version)

    # ------------------------------------------------------------------
    # GET /versions — list all versions of a parent entity
    # ------------------------------------------------------------------

    async def list_versions(
        workspace: str,
        name: str,
        repository: EntityRepository,
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=1000),
    ):
        parent = await _get_parent_or_404(repository, workspace, name)
        parent_filter = ComparisonOperation(
            operator=FilterOperator.EQ,
            field="parent",
            value=parent.id,
        )
        entities, total = await repository.list_entities(
            workspace=workspace,
            entity_type=version_entity_type,
            page=page,
            page_size=page_size,
            sort="created_at",
            filter_op=parent_filter,
        )
        versions = [to_version_response(e, parent) for e in entities]
        return Page(
            data=versions,
            pagination=PaginationData(
                page=page,
                page_size=page_size,
                total_results=total,
                total_pages=(total + page_size - 1) // page_size,
                current_page_size=len(versions),
            ),
            sort="created_at",
            filter=None,
        )

    list_versions.__annotations__["return"] = Page[version_schema]  # ty: ignore[invalid-type-form]

    router.get(
        f"{base}/versions",
        response_model=Page[version_schema],  # ty: ignore[invalid-type-form]
        tags=[api_tag],
        summary=f"List all {parent_entity_type} versions",
        description="Returns all versions sorted by creation time (oldest first).",
    )(list_versions)

    # ------------------------------------------------------------------
    # GET /versions/{version_number} — fetch a specific version
    # ------------------------------------------------------------------

    async def get_version(
        workspace: str,
        name: str,
        version_number: int,
        repository: EntityRepository,
    ):
        if version_number < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="version_number must be >= 1",
            )
        parent = await _get_parent_or_404(repository, workspace, name)
        # Resolve by (parent, version_number) rather than reconstructing the child
        # name from the parent's name. The version_number is the stable identity;
        # the parent (and therefore the embedded name) may be renamed over time.
        version_filter = LogicalOperation(
            operator=FilterOperator.AND,
            operations=[
                ComparisonOperation(operator=FilterOperator.EQ, field="parent", value=parent.id),
                ComparisonOperation(operator=FilterOperator.EQ, field="data.version_number", value=version_number),
            ],
        )
        entities, _ = await repository.list_entities(
            workspace=workspace,
            entity_type=version_entity_type,
            page=1,
            page_size=1,
            filter_op=version_filter,
        )
        if not entities:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} not found for '{name}'",
            )
        return to_version_response(entities[0], parent)

    get_version.__annotations__["return"] = version_schema

    router.get(
        f"{base}/versions/{{version_number}}",
        response_model=version_schema,
        tags=[api_tag],
        summary=f"Get a specific {parent_entity_type} version",
    )(get_version)

    return router
