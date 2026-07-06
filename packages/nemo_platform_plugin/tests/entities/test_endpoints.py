# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Entity Store endpoint definitions."""

from __future__ import annotations

from typing import get_origin

from nemo_platform_plugin.client.types import Paginated, PreparedRequest
from nemo_platform_plugin.entities import endpoints
from nemo_platform_plugin.entities.types import (
    DeleteResponse,
    EntityCreateInput,
    EntityResponse,
    EntityUpdate,
)


def test_create_entity() -> None:
    body = EntityCreateInput(name="my-config", data={"foo": "bar"})
    prepared = endpoints.create_entity(workspace="default", entity_type="config", body=body)

    assert isinstance(prepared, PreparedRequest)
    assert prepared.method == "POST"
    assert prepared.path_template == "/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}"
    assert prepared.path_params == {"workspace": "default", "entity_type": "config"}
    assert prepared.content == body.model_dump_json(exclude_unset=True).encode()
    assert prepared.content_type == "application/json"
    assert prepared.response_type is EntityResponse


def test_create_entity_workspace_optional() -> None:
    body = EntityCreateInput(data={})
    prepared = endpoints.create_entity(entity_type="config", body=body)

    assert prepared.path_params == {"entity_type": "config"}


def test_list_entities() -> None:
    prepared = endpoints.list_entities(workspace="default", entity_type="model")

    assert prepared.method == "GET"
    assert prepared.path_template == "/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}"
    assert prepared.path_params == {"workspace": "default", "entity_type": "model"}
    assert prepared.content is None
    assert get_origin(prepared.response_type) is Paginated


def test_list_entities_with_query_params() -> None:
    prepared = endpoints.list_entities(
        workspace="default", entity_type="model", query_params={"page": 2, "page_size": 10, "sort": "-created_at"}
    )

    assert prepared.query_params == {"page": 2, "page_size": 10, "sort": "-created_at"}


def test_get_entity_by_name() -> None:
    prepared = endpoints.get_entity_by_name(workspace="default", entity_type="model", name="m1")

    assert prepared.method == "GET"
    assert prepared.path_template == "/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}/{name}"
    assert prepared.path_params == {"workspace": "default", "entity_type": "model", "name": "m1"}
    assert prepared.response_type is EntityResponse


def test_get_entity_by_name_with_parent() -> None:
    prepared = endpoints.get_entity_by_name(
        workspace="default", entity_type="model", name="m1", query_params={"parent": "p1"}
    )

    assert prepared.query_params == {"parent": "p1"}


def test_get_entity_by_id() -> None:
    prepared = endpoints.get_entity_by_id(id="abc-123")

    assert prepared.method == "GET"
    assert prepared.path_template == "/apis/entities/v2/entities/{id}"
    assert prepared.path_params == {"id": "abc-123"}
    assert prepared.response_type is EntityResponse


def test_update_entity_by_name() -> None:
    body = EntityUpdate(new_name="m2", data={"x": 1}, expected_db_version=3)
    prepared = endpoints.update_entity_by_name(workspace="default", entity_type="model", name="m1", body=body)

    assert prepared.method == "PUT"
    assert prepared.path_template == "/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}/{name}"
    assert prepared.path_params == {"workspace": "default", "entity_type": "model", "name": "m1"}
    assert prepared.content == body.model_dump_json(exclude_unset=True).encode()
    assert prepared.response_type is EntityResponse


def test_delete_entity_by_name() -> None:
    prepared = endpoints.delete_entity_by_name(workspace="default", entity_type="model", name="m1")

    assert prepared.method == "DELETE"
    assert prepared.path_template == "/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}/{name}"
    assert prepared.path_params == {"workspace": "default", "entity_type": "model", "name": "m1"}
    assert prepared.response_type is DeleteResponse
