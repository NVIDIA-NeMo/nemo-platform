# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the example plugin.

These are the single source of truth for the HTTP contract.  Both the SDK
client and (eventually) server route registration can be derived from them.

Request and response models are plain Pydantic — they have no knowledge of
the HTTP layer.
"""

from __future__ import annotations

from typing import NotRequired

from nemo_example_plugin.entities import ExampleItem
from nemo_example_plugin.types.payloads import (
    CreateExampleItemRequest,
    ExampleItemPage,
    HelloResponse,
    UpdateExampleItemRequest,
)
from nemo_platform_plugin.client.endpoint import BasePath, delete, get, patch, post


# -- Path parameter types --------------------------------------------------


class NamePath(BasePath):
    name: str


class WorkspacePath(BasePath):
    workspace: NotRequired[str]


class WorkspaceItemPath(BasePath):
    workspace: NotRequired[str]
    name: str


# -- Hello -----------------------------------------------------------------

HelloEndpoint = get("/hello/{name}", path_type=NamePath, response_type=HelloResponse)

# -- Items CRUD ------------------------------------------------------------

CreateItemEndpoint = post("/v2/workspaces/{workspace}/items", path_type=WorkspacePath, request_type=CreateExampleItemRequest, response_type=ExampleItem)

ListItemsEndpoint = get("/v2/workspaces/{workspace}/items", path_type=WorkspacePath, response_type=ExampleItemPage)

GetItemEndpoint = get("/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath, response_type=ExampleItem)

UpdateItemEndpoint = patch("/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath, request_type=UpdateExampleItemRequest, response_type=ExampleItem)

DeleteItemEndpoint = delete("/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath)
