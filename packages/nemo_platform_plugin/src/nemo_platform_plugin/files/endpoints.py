# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the Files service.

These are the single source of truth for the HTTP contract.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterable, Iterable

from nemo_platform_plugin.client.endpoint import delete, get, patch, post, put
from nemo_platform_plugin.client.types import BinaryContent, Paginated
from nemo_platform_plugin.files.types import (
    CreateFilesetRequest,
    FilesetFileOutput,
    FilesetOutput,
    ListFilesetFilesResponse,
    ListFilesetsQueryParams,
    ListFilesQueryParams,
    UpdateFilesetRequest,
)

# ---------------------------------------------------------------------------
# Fileset CRUD
# ---------------------------------------------------------------------------


@post("/apis/files/v2/workspaces/{workspace}/filesets")
@abstractmethod
def create_fileset(*, workspace: str | None = None, body: CreateFilesetRequest) -> FilesetOutput: ...


@get("/apis/files/v2/workspaces/{workspace}/filesets")
@abstractmethod
def list_filesets(
    *, workspace: str | None = None, query_params: ListFilesetsQueryParams | None = None
) -> Paginated[FilesetOutput]: ...


@get("/apis/files/v2/workspaces/{workspace}/filesets/{name}")
@abstractmethod
def get_fileset(*, workspace: str | None = None, name: str) -> FilesetOutput: ...


@patch("/apis/files/v2/workspaces/{workspace}/filesets/{name}")
@abstractmethod
def update_fileset(*, workspace: str | None = None, name: str, body: UpdateFilesetRequest) -> FilesetOutput: ...


@delete("/apis/files/v2/workspaces/{workspace}/filesets/{name}")
@abstractmethod
def delete_fileset(*, workspace: str | None = None, name: str) -> FilesetOutput: ...


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


@get("/apis/files/v2/workspaces/{workspace}/filesets/{name}/files")
@abstractmethod
def list_files(
    *, workspace: str | None = None, name: str, query_params: ListFilesQueryParams | None = None
) -> ListFilesetFilesResponse: ...


@put("/apis/files/v2/workspaces/{workspace}/filesets/{name}/-/{path}")
@abstractmethod
def upload_file(
    *, workspace: str | None = None, name: str, path: str, content: bytes | Iterable[bytes] | AsyncIterable[bytes]
) -> FilesetFileOutput: ...


@get("/apis/files/v2/workspaces/{workspace}/filesets/{name}/-/{path}")
@abstractmethod
def download_file(*, workspace: str | None = None, name: str, path: str) -> BinaryContent: ...


@delete("/apis/files/v2/workspaces/{workspace}/filesets/{name}/-/{path}")
@abstractmethod
def delete_file(*, workspace: str | None = None, name: str, path: str) -> FilesetFileOutput: ...
