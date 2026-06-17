# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the example plugin.

These are the single source of truth for the HTTP contract.  Both the SDK
client and (eventually) server route registration can be derived from them.

Request and response models are plain Pydantic — they have no knowledge of
the HTTP layer.
"""

from __future__ import annotations

from nemo_example_plugin.entities import ExampleItem
from nemo_example_plugin.types.payloads import (
    CreateExampleItemRequest,
    ExampleItemPage,
    HelloResponse,
    UpdateExampleItemRequest,
)
from nemo_platform_plugin.client.endpoint import delete, get, patch, post
from nemo_platform_plugin.client.types import PathParams, WorkspaceParams

# -- Path parameter types --------------------------------------------------


class NamePath(PathParams):
    name: str


class WorkspaceItemPath(WorkspaceParams):
    name: str


# -- Hello -----------------------------------------------------------------

HelloEndpoint = get("/apis/example/hello/{name}", path_type=NamePath, response_type=HelloResponse)

# -- Items CRUD ------------------------------------------------------------

CreateItemEndpoint = post(
    "/apis/example/v2/workspaces/{workspace}/items",
    path_type=WorkspaceParams,
    request_type=CreateExampleItemRequest,
    response_type=ExampleItem,
)

ListItemsEndpoint = get(
    "/apis/example/v2/workspaces/{workspace}/items", path_type=WorkspaceParams, response_type=ExampleItemPage
)

GetItemEndpoint = get(
    "/apis/example/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath, response_type=ExampleItem
)

UpdateItemEndpoint = patch(
    "/apis/example/v2/workspaces/{workspace}/items/{name}",
    path_type=WorkspaceItemPath,
    request_type=UpdateExampleItemRequest,
    response_type=ExampleItem,
)

DeleteItemEndpoint = delete("/apis/example/v2/workspaces/{workspace}/items/{name}", path_type=WorkspaceItemPath)
