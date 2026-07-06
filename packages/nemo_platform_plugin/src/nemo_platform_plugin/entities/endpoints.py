# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the Entity Store service (generic routes).

Single source of truth for the HTTP contract of the generic entity routes.
Projects and workspaces routers are out of scope — the entity client only
uses the generic ``/entities`` routes.
"""

from __future__ import annotations

from abc import abstractmethod

from nemo_platform_plugin.client.endpoint import delete, get, post, put
from nemo_platform_plugin.client.types import Paginated
from nemo_platform_plugin.entities.types import (
    DeleteResponse,
    EntityCreateInput,
    EntityResponse,
    EntityUpdate,
    ListEntitiesQueryParams,
    ParentQueryParams,
)


@post("/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}")
@abstractmethod
def create_entity(*, workspace: str | None = None, entity_type: str, body: EntityCreateInput) -> EntityResponse: ...


@get("/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}")
@abstractmethod
def list_entities(
    *, workspace: str | None = None, entity_type: str, query_params: ListEntitiesQueryParams | None = None
) -> Paginated[EntityResponse]: ...


@get("/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}/{name}")
@abstractmethod
def get_entity_by_name(
    *, workspace: str | None = None, entity_type: str, name: str, query_params: ParentQueryParams | None = None
) -> EntityResponse: ...


@get("/apis/entities/v2/entities/{id}")
@abstractmethod
def get_entity_by_id(*, id: str) -> EntityResponse: ...


@put("/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}/{name}")
@abstractmethod
def update_entity_by_name(
    *,
    workspace: str | None = None,
    entity_type: str,
    name: str,
    body: EntityUpdate,
    query_params: ParentQueryParams | None = None,
) -> EntityResponse: ...


@delete("/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}/{name}")
@abstractmethod
def delete_entity_by_name(
    *, workspace: str | None = None, entity_type: str, name: str, query_params: ParentQueryParams | None = None
) -> DeleteResponse: ...
