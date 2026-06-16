# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the example plugin.

These are the single source of truth for the HTTP contract.  Both the SDK
client and (eventually) server route registration can be derived from them.

Request and response models are plain Pydantic — they have no knowledge of
the HTTP layer.
"""

from __future__ import annotations

from typing import TypedDict

from nemo_example_plugin.entities import ExampleItem
from nemo_example_plugin.types.payloads import (
    CreateExampleItemRequest,
    ExampleItemPage,
    HelloResponse,
    UpdateExampleItemRequest,
)
from nemo_platform_plugin.client.endpoint import delete, get, patch, post


# -- Path parameter types --------------------------------------------------


class NamePath(TypedDict):
    name: str


class WorkspacePath(TypedDict):
    workspace: str


class WorkspaceItemPath(TypedDict):
    workspace: str
    name: str


# -- Hello -----------------------------------------------------------------

HelloEndpoint = get("/hello/{name}", NamePath, HelloResponse)

# -- Items CRUD ------------------------------------------------------------

CreateItemEndpoint = post("/v2/workspaces/{workspace}/items", WorkspacePath, CreateExampleItemRequest, ExampleItem)

ListItemsEndpoint = get("/v2/workspaces/{workspace}/items", WorkspacePath, ExampleItemPage)

GetItemEndpoint = get("/v2/workspaces/{workspace}/items/{name}", WorkspaceItemPath, ExampleItem)

UpdateItemEndpoint = patch("/v2/workspaces/{workspace}/items/{name}", WorkspaceItemPath, UpdateExampleItemRequest, ExampleItem)

DeleteItemEndpoint = delete("/v2/workspaces/{workspace}/items/{name}", WorkspaceItemPath)
