# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the example plugin.

These are the single source of truth for the HTTP contract.  Each endpoint
declares its call signature and response type as a decorated function stub.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from nemo_example_plugin.entities import ExampleItem
from nemo_example_plugin.types.payloads import (
    BlobUploadResponse,
    CountRequest,
    CreateExampleItemRequest,
    ExampleItemPage,
    HelloResponse,
    Tick,
    UpdateExampleItemRequest,
)
from nemo_platform_plugin.client.endpoint import delete, get, patch, post, put
from nemo_platform_plugin.client.types import BinaryContent, Stream

# -- Hello -----------------------------------------------------------------


@get("/apis/example/hello/{name}")
def HelloEndpoint(*, name: str) -> HelloResponse: ...


# -- Items CRUD ------------------------------------------------------------


@post("/apis/example/v2/workspaces/{workspace}/items")
def CreateItemEndpoint(body: CreateExampleItemRequest, *, workspace: str) -> ExampleItem: ...


class ListItemsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]


@get("/apis/example/v2/workspaces/{workspace}/items")
def ListItemsEndpoint(*, workspace: str, query_params: ListItemsQueryParams | None = None) -> ExampleItemPage: ...


@get("/apis/example/v2/workspaces/{workspace}/items/{name}")
def GetItemEndpoint(*, workspace: str, name: str) -> ExampleItem: ...


@patch("/apis/example/v2/workspaces/{workspace}/items/{name}")
def UpdateItemEndpoint(body: UpdateExampleItemRequest, *, workspace: str, name: str) -> ExampleItem: ...


@delete("/apis/example/v2/workspaces/{workspace}/items/{name}")
def DeleteItemEndpoint(*, workspace: str, name: str) -> None: ...


# -- Functions -------------------------------------------------------------


@post("/apis/example/v2/workspaces/{workspace}/count")
def CountEndpoint(body: CountRequest, *, workspace: str) -> Stream[Tick]: ...


# -- Binary ----------------------------------------------------------------


@put("/apis/example/blob/{name}")
def UploadBlobEndpoint(content: bytes, *, name: str) -> BlobUploadResponse: ...


@get("/apis/example/blob/{name}")
def DownloadBlobEndpoint(*, name: str) -> BinaryContent: ...
