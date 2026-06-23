# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the example plugin.

These are the single source of truth for the HTTP contract.  Each endpoint
declares its call signature and response type as a decorated method on the
endpoint collection class.
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


class ListItemsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]


class ExampleEndpoints:
    """Endpoint collection for the example plugin API."""

    @get("/apis/example/hello/{name}")
    def hello(self, *, name: str) -> HelloResponse:
        raise NotImplementedError

    @post("/apis/example/v2/workspaces/{workspace}/items")
    def create_item(self, *, workspace: str | None = None, body: CreateExampleItemRequest) -> ExampleItem:
        raise NotImplementedError

    @get("/apis/example/v2/workspaces/{workspace}/items")
    def list_items(
        self, *, workspace: str | None = None, query_params: ListItemsQueryParams | None = None
    ) -> ExampleItemPage:
        raise NotImplementedError

    @get("/apis/example/v2/workspaces/{workspace}/items/{name}")
    def get_item(self, *, workspace: str | None = None, name: str) -> ExampleItem:
        raise NotImplementedError

    @patch("/apis/example/v2/workspaces/{workspace}/items/{name}")
    def update_item(self, *, workspace: str | None = None, name: str, body: UpdateExampleItemRequest) -> ExampleItem:
        raise NotImplementedError

    @delete("/apis/example/v2/workspaces/{workspace}/items/{name}")
    def delete_item(self, *, workspace: str | None = None, name: str) -> None:
        raise NotImplementedError

    @post("/apis/example/v2/workspaces/{workspace}/count")
    def count(self, *, workspace: str | None = None, body: CountRequest) -> Stream[Tick]:
        raise NotImplementedError

    @put("/apis/example/blob/{name}")
    def upload_blob(self, *, name: str, content: bytes) -> BlobUploadResponse:
        raise NotImplementedError

    @get("/apis/example/blob/{name}")
    def download_blob(self, *, name: str) -> BinaryContent:
        raise NotImplementedError
