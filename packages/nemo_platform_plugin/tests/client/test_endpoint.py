# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_platform_plugin.client.endpoint import delete, get, patch, post
from nemo_platform_plugin.client.types import PathParams, PreparedRequest
from pydantic import BaseModel


class FakeRequest(BaseModel):
    name: str


class FakeResponse(BaseModel):
    id: int
    name: str


class WorkspacePath(PathParams):
    workspace: str


class WorkspaceItemPath(PathParams):
    workspace: str
    name: str


class IdPath(PathParams):
    id: str


def test_post_endpoint_produces_prepared_request() -> None:
    ep = post(
        "/v2/workspaces/{workspace}/items",
        path_type=WorkspacePath,
        request_type=FakeRequest,
        response_type=FakeResponse,
    )
    payload = FakeRequest(name="alice")
    prepared = ep.request(payload, workspace="default")

    assert isinstance(prepared, PreparedRequest)
    assert prepared.path_template == "/v2/workspaces/{workspace}/items"
    assert prepared.path_params == {"workspace": "default"}
    assert prepared.method == "POST"
    assert prepared.content == payload.model_dump_json().encode()
    assert prepared.content_type == "application/json"
    assert prepared.response_type is FakeResponse


def test_get_endpoint_no_body() -> None:
    ep = get("/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath, response_type=FakeResponse)
    prepared = ep.request(workspace="default", name="item-1")

    assert prepared.path_template == "/v2/workspaces/{workspace}/items/{name}"
    assert prepared.path_params == {"workspace": "default", "name": "item-1"}
    assert prepared.method == "GET"
    assert prepared.content is None
    assert prepared.content_type is None
    assert prepared.response_type is FakeResponse


def test_delete_endpoint() -> None:
    ep = delete("/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath)
    prepared = ep.request(workspace="default", name="item-1")

    assert prepared.path_params == {"workspace": "default", "name": "item-1"}
    assert prepared.method == "DELETE"
    assert prepared.content is None


def test_patch_endpoint() -> None:
    ep = patch("/items/{id}", path_type=IdPath, request_type=FakeRequest, response_type=FakeResponse)
    payload = FakeRequest(name="updated")
    prepared = ep.request(payload, id="42")

    assert prepared.path_params == {"id": "42"}
    assert prepared.method == "PATCH"
    assert prepared.content == payload.model_dump_json().encode()


def test_endpoint_repr() -> None:
    ep = post("/items/{id}", path_type=IdPath, request_type=FakeRequest, response_type=FakeResponse)
    r = repr(ep)
    assert "/items" in r
    assert "FakeRequest" in r
    assert "FakeResponse" in r
