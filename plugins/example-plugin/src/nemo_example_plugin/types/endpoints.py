# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the example plugin.

These are the single source of truth for the HTTP contract.  Each endpoint
is a decorated function that declares its call signature and response type.
"""

from __future__ import annotations

from abc import abstractmethod
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


class ListItemsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]


@get("/apis/example/hello/{name}")
@abstractmethod
def hello(*, name: str) -> HelloResponse: ...


@post("/apis/example/v2/workspaces/{workspace}/items")
@abstractmethod
def create_item(*, workspace: str | None = None, body: CreateExampleItemRequest) -> ExampleItem: ...


@get("/apis/example/v2/workspaces/{workspace}/items")
@abstractmethod
def list_items(
    *, workspace: str | None = None, query_params: ListItemsQueryParams | None = None
) -> ExampleItemPage: ...


@get("/apis/example/v2/workspaces/{workspace}/items/{name}")
@abstractmethod
def get_item(*, workspace: str | None = None, name: str) -> ExampleItem: ...


@patch("/apis/example/v2/workspaces/{workspace}/items/{name}")
@abstractmethod
def update_item(*, workspace: str | None = None, name: str, body: UpdateExampleItemRequest) -> ExampleItem: ...


@delete("/apis/example/v2/workspaces/{workspace}/items/{name}")
@abstractmethod
def delete_item(*, workspace: str | None = None, name: str) -> None: ...


@post("/apis/example/v2/workspaces/{workspace}/count")
@abstractmethod
def count(*, workspace: str | None = None, body: CountRequest) -> Stream[Tick]: ...


@put("/apis/example/blob/{name}")
@abstractmethod
def upload_blob(*, name: str, content: bytes) -> BlobUploadResponse: ...


@get("/apis/example/blob/{name}")
@abstractmethod
def download_blob(*, name: str) -> BinaryContent: ...
