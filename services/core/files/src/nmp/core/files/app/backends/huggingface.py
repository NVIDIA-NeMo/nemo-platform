# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Huggingface storage backend for Huggingface Hub repositories."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import (
    AsyncIterator,
)

import aiohttp
from anyio import to_thread
from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_url
from huggingface_hub.utils import (
    EntryNotFoundError,
    HfHubHTTPError,
)
from nmp.common.files.storage_config import (
    HuggingfaceStorageConfig as HuggingfaceStorageConfig,
)
from nmp.core.files.app.backends.base import (
    ByteRange,
    FileInfo,
    StorageImpl,
)
from nmp.core.files.app.external_hosts import validate_external_host
from nmp.core.files.app.http_session import get_http_session
from nmp.core.files.app.streaming import download_url_streaming
from nmp.core.files.exceptions import (
    NotFoundError,
    StorageAccessError,
    StorageBackendError,
    StorageConfigError,
    StorageUnavailableError,
)

logger = logging.getLogger(__name__)


class HuggingfaceBackendError(StorageBackendError):
    """Raised when there's issues talking to Huggingface."""


class HuggingfaceAccessError(StorageAccessError):
    """Raised when access to a HuggingFace repo is denied (gated, 401, 403)."""


class HuggingfaceConfigError(StorageConfigError):
    """Raised when HuggingFace storage config is invalid (repo/revision not found)."""


class HuggingfaceUnavailableError(StorageUnavailableError):
    """Raised when HuggingFace is unavailable (5xx, 429, timeout)."""


def raise_for_hf_status(
    status_code: int,
    headers: dict[str, str] | None = None,
    url: str | None = None,
) -> None:
    """Raise appropriate HuggingFace exception based on status code and headers.

    Uses the X-Error-Code header that HuggingFace returns to determine the
    specific error type, falling back to status code mapping.

    This code is slightly duplicated from huggingface_hub.util's hf_raise_for_status
    because we use both aiohttp and huggingface_hub for different requests. This
    lets us use this singular helper function for all error-handling throughout this file.
    """
    if status_code < 400:
        return

    error_code = headers.get("X-Error-Code") if headers else None
    context = f" for {url}" if url else ""

    # Map X-Error-Code header to specific exceptions
    if error_code == "GatedRepo":
        raise HuggingfaceAccessError(f"Access denied to gated repository{context}")
    if error_code == "RepoNotFound":
        raise HuggingfaceConfigError(f"Repository not found{context}")
    if error_code == "RevisionNotFound":
        raise HuggingfaceConfigError(f"Revision not found{context}")
    if error_code == "EntryNotFound":
        raise HuggingfaceConfigError(f"Entry not found{context}")

    # Fall back to status code mapping
    if status_code == 401:
        raise HuggingfaceAccessError(f"Unauthorized{context}")
    if status_code == 403:
        raise HuggingfaceAccessError(f"Forbidden{context}")
    if status_code == 404:
        raise HuggingfaceConfigError(f"Not found{context}")
    if status_code == 429:
        raise HuggingfaceUnavailableError(f"Rate limited{context}")
    if status_code >= 500:
        raise HuggingfaceUnavailableError(f"Service error ({status_code}){context}")

    raise HuggingfaceBackendError(f"HTTP {status_code}{context}")


@dataclass
class HuggingfaceStorageImpl(StorageImpl):
    config: HuggingfaceStorageConfig
    secrets: dict[str, str]
    _api: HfApi = field(init=False)

    def __post_init__(self):
        self._api = HfApi(
            token=self.secrets.get("token"),
            endpoint=self.config.endpoint,
        )

    async def resolve_config(self) -> HuggingfaceStorageConfig:
        """Resolve the revision to a specific commit SHA.

        Queries HuggingFace to get the commit SHA for the configured revision
        (which may be a branch name like 'main' or a tag). Stores the original
        revision for auditing and updates the config with the resolved SHA.

        Returns:
            A new HuggingfaceStorageConfig with the resolved commit SHA.

        Raises:
            HuggingfaceConfigError: If the repository or revision is not found.
        """
        try:
            info = await to_thread.run_sync(
                lambda: self._api.repo_info(
                    repo_id=self.config.repo_id,
                    repo_type=self.config.repo_type,
                    revision=self.config.revision,
                )
            )
            return self.config.model_copy(
                update={
                    "original_revision": self.config.revision,
                    "revision": info.sha,
                }
            )
        except HfHubHTTPError as exc:
            if exc.response is not None:
                raise_for_hf_status(
                    exc.response.status_code,
                    dict(exc.response.headers),
                    str(exc.response.url),
                )
            raise HuggingfaceBackendError(f"HuggingFace API error: {exc}") from exc

    def _get_download_url(self, filepath: str) -> str:
        """Generate a download URL for a file in the Huggingface repo."""
        return hf_hub_url(
            repo_id=self.config.repo_id,
            filename=filepath,
            repo_type=self.config.repo_type,
            revision=self.config.revision,
            endpoint=self.config.endpoint,
        )

    async def _get_hf_file_metadata(self, filepath: str):
        """Get file metadata from Huggingface for a specific file."""
        url = self._get_download_url(filepath)
        return await to_thread.run_sync(lambda: get_hf_file_metadata(url=url, token=self.secrets.get("token")))

    async def list_files(self, path: str | None = None) -> list[FileInfo]:
        """List files in the Huggingface repository."""
        try:
            # list_repo_tree returns RepoFile and RepoFolder objects
            # We filter for files only (items with size attribute)
            items = await to_thread.run_sync(
                lambda: list(
                    self._api.list_repo_tree(
                        repo_id=self.config.repo_id,
                        repo_type=self.config.repo_type,
                        revision=self.config.revision,
                        path_in_repo=path,
                        recursive=True,
                    )
                )
            )
        except EntryNotFoundError:
            # list_repo_tree expects a directory path. If path points to a file
            # (not a directory), HuggingFace returns 404. Fall back to checking
            # if it's a single file using get_file.
            if path:
                try:
                    file_info = await self.get_file(path)
                    return [file_info]
                except NotFoundError:
                    # Neither a directory nor a file - return empty list
                    return []
            return []
        except HfHubHTTPError as exc:
            if exc.response is not None:
                raise_for_hf_status(
                    exc.response.status_code,
                    dict(exc.response.headers),
                    str(exc.response.url),
                )
            raise HuggingfaceBackendError(f"HuggingFace API error: {exc}") from exc

        file_infos = []
        for item in items:
            # Only include files (RepoFile has size, RepoFolder does not)
            if not hasattr(item, "size") or item.size is None:
                continue
            file_infos.append(
                FileInfo(
                    path=item.path,
                    size=item.size,
                )
            )

        return file_infos

    async def get_file(self, path: str) -> FileInfo:
        """Get metadata for a specific file using Huggingface's file metadata API.

        Override the base class method because list_repo_tree doesn't work
        for individual file paths - it expects directory paths.

        """
        url = self._get_download_url(path)

        try:
            metadata = await to_thread.run_sync(lambda: get_hf_file_metadata(url=url, token=self.secrets.get("token")))
        except EntryNotFoundError as exc:
            raise NotFoundError(f"File '{path}' not found in {self.config.repo_id}@{self.config.revision}") from exc
        except HfHubHTTPError as exc:
            if exc.response is not None:
                raise_for_hf_status(
                    exc.response.status_code,
                    dict(exc.response.headers),
                    str(exc.response.url),
                )
            raise HuggingfaceBackendError(f"HuggingFace API error: {exc}") from exc

        return FileInfo(path=path, size=metadata.size)

    async def download(self, path: str, byte_range: ByteRange | None) -> AsyncIterator[bytes]:
        """Download a file from Huggingface.

        This method:
        1. Generates a download URL using hf_hub_url
        2. Downloads the file via HTTP with optional auth header
        3. Streams the content back as an async iterator
        """
        download_url = self._get_download_url(path)

        headers = {}
        if self.secrets.get("token"):
            headers["Authorization"] = f"Bearer {self.secrets.get('token')}"

        async def _download() -> AsyncIterator[bytes]:
            session = get_http_session()
            try:
                async for chunk in download_url_streaming(
                    url=download_url,
                    session=session,
                    headers=headers if headers else None,
                    byte_range=byte_range,
                    chunk_size=self.config.read_chunk_size,
                ):
                    yield chunk
            except aiohttp.ClientResponseError as exc:
                response_headers = dict(exc.headers) if exc.headers else None
                raise_for_hf_status(exc.status, response_headers, download_url)
            except aiohttp.ClientError as exc:
                raise HuggingfaceBackendError(f"Network error downloading file {path}") from exc

        return _download()

    async def validate_storage(self):
        """Validate that we can access the Huggingface repository.

        This performs three checks:
        1. Validate endpoint is in the Files service allowed_external_hosts.
        2. Verify the repository exists and is accessible via repo_info.
        3. Verify we can actually download files by getting metadata for a file.

        The third check is important for gated repos where repo_info may succeed
        but file downloads require explicit access approval.
        """
        validate_external_host(self.config.endpoint)
        try:
            repo_info = await to_thread.run_sync(
                lambda: self._api.repo_info(
                    repo_id=self.config.repo_id,
                    repo_type=self.config.repo_type,
                    revision=self.config.revision,
                )
            )

            # Verify we can actually download files by checking a file's metadata.
            # This catches gated repos where repo_info succeeds but downloads are blocked.
            if repo_info.siblings:
                sibling = repo_info.siblings[0]
                await self._get_hf_file_metadata(sibling.rfilename)

        except HfHubHTTPError as exc:
            if exc.response is not None:
                raise_for_hf_status(
                    exc.response.status_code,
                    dict(exc.response.headers),
                    str(exc.response.url),
                )
            raise HuggingfaceBackendError(f"HuggingFace API error: {exc}") from exc
        except Exception as exc:
            raise HuggingfaceBackendError(
                f"Failed to access Huggingface repository {self.config.repo_id}@{self.config.revision}"
            ) from exc

    async def upload(
        self,
        path: str,
        fstream: AsyncIterator[bytes],
        content_length: int | None = None,
    ) -> FileInfo:
        raise NotImplementedError("Huggingface upload is not implemented")

    async def delete(self, path: str) -> FileInfo:
        raise NotImplementedError("Huggingface delete is not implemented")

    async def get_cache_path_key(self, path: str | None = None) -> str:
        """
        Return cache path that includes repo ID and revision for uniqueness.

        Format: cache/hf/{repo_id}/{revision}/{path}
        This ensures different revisions don't overwrite each other in cache.
        The repo_id naturally creates nested folders (e.g., facebook/opt-125m).

        Args:
            path: File path within the repo. If None, returns the cache root prefix.
        """
        prefix = f"cache/hf/{self.config.repo_id}/{self.config.revision}"
        if path is None:
            return prefix
        return f"{prefix}/{path}"
