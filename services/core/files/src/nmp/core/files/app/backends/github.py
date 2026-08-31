# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""GitHub storage backend for repositories served over the GitHub REST API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import aiohttp
from nmp.common.files.storage_config import GithubStorageConfig as GithubStorageConfig
from nmp.core.files.app.backends.base import (
    ByteRange,
    FileInfo,
    StorageImpl,
)
from nmp.core.files.app.external_hosts import validate_external_host
from nmp.core.files.app.http_session import get_http_session
from nmp.core.files.exceptions import (
    NotFoundError,
    StorageAccessError,
    StorageBackendError,
    StorageConfigError,
    StorageUnavailableError,
)

logger = logging.getLogger(__name__)

JSON_MEDIA_TYPE = "application/vnd.github+json"
RAW_MEDIA_TYPE = "application/vnd.github.raw"


class GithubBackendError(StorageBackendError):
    """Raised when there's issues talking to GitHub."""


class GithubAccessError(StorageAccessError):
    """Raised when access to a GitHub repository is denied (401, 403)."""


class GithubConfigError(StorageConfigError):
    """Raised when GitHub storage config is invalid (repository or revision not found)."""


class GithubUnavailableError(StorageUnavailableError):
    """Raised when GitHub is unavailable (5xx, 429)."""


def raise_for_github_status(status: int, subject: str, headers: dict[str, str] | None = None) -> None:
    """Map a GitHub response status onto the storage exception hierarchy."""
    if status < 400:
        return

    # A private repository is indistinguishable from a missing one without the right
    # token, so 404 is reported as a config error rather than an access error.
    if status == 404:
        raise GithubConfigError(f"GitHub has no {subject}, or the token cannot see it")
    if status in (401, 403):
        if headers and headers.get("x-ratelimit-remaining") == "0":
            raise GithubUnavailableError(f"GitHub rate limit exhausted while reading {subject}")
        raise GithubAccessError(f"GitHub denied access to {subject}")
    if status == 429 or status >= 500:
        raise GithubUnavailableError(f"GitHub is unavailable ({status}) reading {subject}")
    raise GithubBackendError(f"GitHub returned {status} reading {subject}")


@dataclass
class GithubStorageImpl(StorageImpl):
    config: GithubStorageConfig
    secrets: dict[str, str]

    @property
    def _repo_slug(self) -> str:
        return f"{self.config.owner}/{self.config.repo}"

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        token = self.secrets.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _api_url(self, suffix: str) -> str:
        return f"{self.config.api_base_url.rstrip('/')}/repos/{self._repo_slug}/{suffix}"

    def _repo_path(self, path: str) -> str:
        return f"{self.config.path}/{path}" if self.config.path else path

    async def _get_json(self, url: str, subject: str) -> Any:
        session = get_http_session()
        try:
            async with session.get(url, headers=self._headers(JSON_MEDIA_TYPE)) as response:
                raise_for_github_status(subject=subject, status=response.status, headers=dict(response.headers))
                return await response.json()
        except aiohttp.ClientError as exc:
            raise GithubUnavailableError(f"Could not reach GitHub to read {subject}: {exc}") from exc

    async def resolve_config(self) -> GithubStorageConfig:
        """Pin the revision to a commit SHA so the fileset cannot shift under a deployment."""
        commit = await self._get_json(
            self._api_url(f"commits/{self.config.revision}"),
            f"revision {self.config.revision} of {self._repo_slug}",
        )
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(sha, str) or not sha:
            raise GithubConfigError(f"GitHub returned no commit SHA for {self.config.revision} of {self._repo_slug}")

        return self.config.model_copy(
            update={"revision": sha, "original_revision": self.config.original_revision or self.config.revision}
        )

    async def list_files(self, path: str | None = None) -> list[FileInfo]:
        tree = await self._get_json(
            self._api_url(f"git/trees/{self.config.revision}?recursive=1"),
            f"{self._repo_slug} at {self.config.revision}",
        )

        if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
            raise GithubBackendError(f"GitHub returned no file list for {self._repo_slug}")
        if tree.get("truncated") is True:
            raise GithubConfigError(
                f"{self._repo_slug} is too large for GitHub to list in one request; "
                "point the fileset at a directory within it"
            )

        prefix = f"{self.config.path}/" if self.config.path else ""
        wanted = f"{path.strip('/')}" if path else ""

        files: list[FileInfo] = []
        for entry in tree["tree"]:
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            entry_path = entry.get("path")
            if not isinstance(entry_path, str) or (prefix and not entry_path.startswith(prefix)):
                continue

            relative = entry_path[len(prefix) :]
            if wanted and relative != wanted and not relative.startswith(f"{wanted}/"):
                continue
            size = entry.get("size")
            files.append(FileInfo(path=relative, size=size if isinstance(size, int) else 0))

        if wanted and not files:
            raise NotFoundError(f"File not found for path: {path}")
        return files

    async def download(self, path: str, byte_range: ByteRange | None) -> AsyncIterator[bytes]:
        """Stream a file's bytes from the contents API, which serves private repos too."""
        url = self._api_url(f"contents/{self._repo_path(path)}?ref={self.config.revision}")
        headers = self._headers(RAW_MEDIA_TYPE)
        if byte_range is not None:
            headers["Range"] = f"bytes={byte_range.start}-{byte_range.end}"

        async def _download() -> AsyncIterator[bytes]:
            session = get_http_session()
            try:
                async with session.get(url, headers=headers) as response:
                    raise_for_github_status(
                        status=response.status,
                        subject=f"{path} in {self._repo_slug}",
                        headers=dict(response.headers),
                    )
                    async for chunk in response.content.iter_chunked(self.config.read_chunk_size):
                        yield chunk
            except aiohttp.ClientError as exc:
                raise GithubUnavailableError(f"Could not download {path} from GitHub: {exc}") from exc

        return _download()

    async def validate_storage(self):
        validate_external_host(self.config.api_base_url)
        await self._get_json(self._api_url("").rstrip("/"), f"repository {self._repo_slug}")

    async def upload(
        self,
        path: str,
        fstream: AsyncIterator[bytes],
        content_length: int | None = None,
    ) -> FileInfo:
        raise NotImplementedError("GitHub upload is not implemented")

    async def delete(self, path: str) -> FileInfo:
        raise NotImplementedError("GitHub delete is not implemented")

    async def get_cache_path_key(self, path: str | None = None) -> str:
        prefix = f"cache/github/{self._repo_slug}/{self.config.revision}"
        if self.config.path:
            prefix = f"{prefix}/{self.config.path}"
        return prefix if path is None else f"{prefix}/{path}"
