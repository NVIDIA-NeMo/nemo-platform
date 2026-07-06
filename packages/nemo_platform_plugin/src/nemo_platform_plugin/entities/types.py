# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Entity Store service.

These types define the HTTP contract for the generic entity routes. They
mirror the server schemas in ``nmp.core.entities.api.v2.entities.schemas`` and
the ``Entity`` response model — kept in sync by hand rather than imported, since
``nemo_platform_plugin`` sits below the services in the dependency graph.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field

# Entity name validation, mirroring nmp.common.entities.constants.NAME_PATTERN.
NAME_PATTERN = r"^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class EntityCreateInput(BaseModel):
    """Body for creating an entity. Workspace and entity_type are path params."""

    name: str | None = Field(
        default=None,
        description="Entity name (optional — auto-generated if not provided).",
        pattern=NAME_PATTERN,
    )
    parent: str | None = Field(default=None, description="Parent entity ID for nested entities")
    project: str | None = Field(default=None, description="Name of the project associated with this entity")
    data: dict[str, Any] = Field(..., description="Entity-specific data (opaque to the entity store)")

    model_config = ConfigDict(regex_engine="python-re")


class EntityUpdate(BaseModel):
    """Body for updating an entity."""

    new_name: str | None = Field(default=None, description="Updated entity name (optional).", pattern=NAME_PATTERN)
    project: str | None = Field(default=None, description="Name of the project associated with this entity")
    data: dict[str, Any] = Field(..., description="Updated entity-specific data")
    expected_db_version: int | None = Field(
        default=None,
        description="Optional DB version for optimistic locking; update only succeeds if the current version matches.",
    )

    model_config = ConfigDict(regex_engine="python-re")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class EntityResponse(BaseModel):
    """Wire shape of an entity returned by the Entity Store API."""

    entity_type: str = Field(..., description="Entity type identifier")
    id: str = Field(..., description="UUID identifier")
    workspace: str = Field(..., description="Workspace identifier")
    parent: str | None = Field(default=None, description="Parent entity ID for nested entities")
    project: str | None = Field(default=None, description="Name of the project associated with this entity")
    name: str = Field(..., description="Entity name")
    data: dict[str, Any] = Field(..., description="Entity data")
    created_at: datetime = Field(..., description="Timestamp of entity creation")
    created_by: str | None = Field(default=None, description="Principal id for entity creator")
    updated_at: datetime = Field(..., description="Timestamp of last entity update")
    updated_by: str | None = Field(default=None, description="Principal id for last entity update")
    db_version: int = Field(..., description="Database version of the entity for optimistic locking")

    model_config = ConfigDict(from_attributes=True)


class DeleteResponse(BaseModel):
    """Response for a successful delete operation."""

    message: str = Field(default="Resource deleted successfully")
    id: str = Field(..., description="ID of the deleted resource")
    deleted_count: int = Field(default=1, description="Number of resources deleted")


# ---------------------------------------------------------------------------
# Query params
# ---------------------------------------------------------------------------


class ListEntitiesQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class ParentQueryParams(TypedDict, total=False):
    parent: NotRequired[str]
