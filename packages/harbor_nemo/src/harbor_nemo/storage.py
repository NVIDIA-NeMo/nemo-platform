# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Blob storage for published archives, backed by the NeMo Files service."""

from __future__ import annotations

from pathlib import Path
from typing import override

from harbor.storage.base import BaseStorage

from harbor_nemo.client import NemoClient, NotFound
from harbor_nemo.config import NemoConfig

#: Separator in a fileset reference: ``workspace/fileset#path-within-fileset``.
FILESET_REF_SEPARATOR = "#"


class NemoStorage(BaseStorage):
    """Reads and writes package blobs in a single NeMo fileset.

    Accepts two shapes of ``remote_path``, which is not an accident:

    * A **bare path** (``packages/nvidia.my-task/<hash>/dist.tar.gz``) is resolved against the
      configured workspace and fileset. ``BasePublisher.remote_path`` — which backends must not
      override — produces exactly this, so uploads always arrive in this form.
    * A **full fileset reference** (``default/harbor-packages#packages/...``) is used as
      given. This is what gets *stored* on a task, and what comes back out of
      ``ResolvedTaskVersion.archive_path`` on the download side.

    Storing the full reference rather than the bare path is deliberate. ``download_file``
    receives only a string, with no workspace or fileset alongside it, so a bare path
    published against one workspace would silently resolve against whichever workspace the
    environment happens to name at download time — asking a fileset for a blob it never
    stored. A self-describing reference cannot be pointed at the wrong host by a changed
    environment variable.
    """

    def __init__(self, client: NemoClient, config: NemoConfig) -> None:
        self._client = client
        self._config = config
        self._ensured_filesets: set[tuple[str, str]] = set()

    def _resolve(self, remote_path: str) -> tuple[str, str, str]:
        """Split ``remote_path`` into ``(workspace, fileset, path)``."""
        if FILESET_REF_SEPARATOR in remote_path:
            location, _, path = remote_path.partition(FILESET_REF_SEPARATOR)
            workspace, _, fileset = location.partition("/")
            if not fileset:
                # "fileset#path" with no workspace: legal in the platform's own path parser,
                # so accept it rather than failing on a form users will reasonably write.
                return self._config.workspace, workspace, path
            return workspace, fileset, path
        return self._config.workspace, self._config.fileset, remote_path

    def _file_url(self, workspace: str, fileset: str, path: str) -> str:
        base = f"{self._config.base_url}/apis/files/v2/workspaces/{workspace}/filesets"
        return f"{base}/{fileset}/-/{path}"

    def to_fileset_ref(self, remote_path: str) -> str:
        """Render ``remote_path`` as the self-describing reference to store on a task."""
        workspace, fileset, path = self._resolve(remote_path)
        return f"{workspace}/{fileset}{FILESET_REF_SEPARATOR}{path}"

    async def _ensure_fileset(self, workspace: str, fileset: str) -> None:
        """Create the fileset if it does not exist, tolerating a concurrent creator.

        ``publish_tasks`` runs up to 50 publishes at once against an empty workspace, so this
        races with itself on the very first publish. A 409 means someone else won, which is
        the outcome we wanted anyway.
        """
        if (workspace, fileset) in self._ensured_filesets:
            return
        base = f"{self._config.base_url}/apis/files/v2/workspaces/{workspace}/filesets"
        try:
            await self._client.request("POST", base, json={"name": fileset})
        except Exception as exc:  # noqa: BLE001 - re-raised below unless it is a benign conflict
            if "already exists" not in str(exc).lower() and "conflict" not in str(exc).lower():
                raise
        self._ensured_filesets.add((workspace, fileset))

    async def exists(self, remote_path: str) -> bool:
        """Whether a blob is already present, via HEAD rather than a full download."""
        workspace, fileset, path = self._resolve(remote_path)
        try:
            await self._client.request("HEAD", self._file_url(workspace, fileset, path))
        except NotFound:
            return False
        return True

    @override
    async def upload_file(self, file_path: Path, remote_path: str) -> None:
        workspace, fileset, path = self._resolve(remote_path)
        await self._ensure_fileset(workspace, fileset)
        await self._client.request(
            "PUT",
            self._file_url(workspace, fileset, path),
            content=file_path.read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )

    @override
    async def download_file(self, remote_path: str, file_path: Path) -> None:
        workspace, fileset, path = self._resolve(remote_path)
        response = await self._client.request("GET", self._file_url(workspace, fileset, path))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(response.content)
