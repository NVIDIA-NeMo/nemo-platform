# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FilesResource classes with FilesetFileSystem support.

These classes provide high-level file operations (upload, download, list, delete)
backed by the NemoClient typed HTTP client and fsspec filesystem access.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import PurePath
from typing import Any, Protocol, runtime_checkable

import nemo_platform
from fsspec.callbacks import Callback
from fsspec.core import has_magic
from nemo_platform_plugin.client.errors import NemoHTTPError
from nemo_platform_plugin.client.response import AsyncNemoPaginatedResponse, NemoPaginatedResponse
from nemo_platform_plugin.files.client import AsyncFilesClient, FilesClient
from nemo_platform_plugin.files.types import (
    CacheStatus,
    CreateFilesetRequest,
    FilesetFileOutput,
    FilesetMetadata,
    FilesetOutput,
    FilesetPurpose,
    StorageConfig,
    UpdateFilesetRequest,
)

from nemo_platform.filesets.filesystem.filesystem import (
    FilesetFileSystem,
    build_fileset_ref,
    parse_fileset_path,
)


def _build_error_map() -> dict[type[NemoHTTPError], type[nemo_platform.APIStatusError]]:
    """Build a mapping from NemoClient errors to Stainless SDK errors.

    Lazy import to avoid hard-coding the Stainless error classes at module level.
    This mapping is temporary — remove when all consumers import errors from
    nemo_platform_plugin.client.errors instead of nemo_platform (AIRCORE-840).
    """
    from nemo_platform_plugin.client import errors

    return {
        errors.BadRequestError: nemo_platform.BadRequestError,
        errors.AuthenticationError: nemo_platform.AuthenticationError,
        errors.PermissionDeniedError: nemo_platform.PermissionDeniedError,
        errors.NotFoundError: nemo_platform.NotFoundError,
        errors.ConflictError: nemo_platform.ConflictError,
        errors.UnprocessableEntityError: nemo_platform.UnprocessableEntityError,
        errors.RateLimitError: nemo_platform.RateLimitError,
        errors.InternalServerError: nemo_platform.InternalServerError,
    }


_ERROR_MAP: dict[type[NemoHTTPError], type[nemo_platform.APIStatusError]] | None = None


def _get_error_map() -> dict[type[NemoHTTPError], type[nemo_platform.APIStatusError]]:
    global _ERROR_MAP
    if _ERROR_MAP is None:
        _ERROR_MAP = _build_error_map()
    return _ERROR_MAP


def _raise_as_stainless(e: NemoHTTPError) -> None:
    """Re-raise a NemoClient error as its Stainless SDK equivalent.

    Preserves backward compatibility for consumers that catch
    ``nemo_platform.NotFoundError`` etc. Remove with AIRCORE-840.
    """
    error_map = _get_error_map()
    stainless_cls = error_map.get(type(e))
    if stainless_cls is not None:
        raise stainless_cls(
            message=str(e),
            response=e.http_response,
            body=e.body,
        ) from e
    raise


class _RemappingFilesClient(FilesClient):
    """FilesClient that re-raises NemoClient errors as Stainless SDK errors.

    Wraps ``send()`` so ALL operations through this client (filesets, files,
    fsspec) raise Stainless-compatible exceptions. Remove with AIRCORE-840.
    """

    # Used by FilesetFileSystem._ensure_async to create the matching async
    # remapping client when converting sync → async.
    _async_cls: type[AsyncFilesClient] | None = None

    def send(self, request, *, headers=None, retry=None):  # type: ignore[override]
        try:
            return super().send(request, headers=headers, retry=retry)
        except NemoHTTPError as e:
            _raise_as_stainless(e)


class _RemappingAsyncFilesClient(AsyncFilesClient):
    """AsyncFilesClient that re-raises NemoClient errors as Stainless SDK errors."""

    async def send(self, request, *, headers=None, retry=None):  # type: ignore[override]
        try:
            return await super().send(request, headers=headers, retry=retry)
        except NemoHTTPError as e:
            _raise_as_stainless(e)


_RemappingFilesClient._async_cls = _RemappingAsyncFilesClient


@dataclass
class ListFilesResponse:
    """Response from listing files in a fileset.

    Attributes:
        data: List of files in the fileset.

    Properties:
        cache_status: Aggregate cache status of all files.
            - "caching" if any file is actively being cached
            - "not_cached" if any file is not cached (and none are caching)
            - "cached" if all files are fully cached
            - "not_cacheable" if all files cannot be cached
            - None if no cache information is available
    """

    data: list[FilesetFileOutput]

    @property
    def cache_status(self) -> CacheStatus | None:
        """Get aggregate cache status of all files.

        Returns the most relevant status based on priority:
        - "caching" if any file is actively being cached
        - "not_cached" if any file is not cached (and none are caching)
        - "cached" if all files are fully cached
        - "not_cacheable" if all files cannot be cached
        - None if no cache information is available
        """
        if not self.data:
            return None

        statuses = [f.cache_status for f in self.data if f.cache_status is not None]
        if not statuses:
            return None

        # Priority: caching > not_cached > cached > not_cacheable
        if "caching" in statuses:
            return "caching"
        if "not_cached" in statuses:
            return "not_cached"
        if all(s == "cached" for s in statuses):
            return "cached"
        if all(s == "not_cacheable" for s in statuses):
            return "not_cacheable"

        # Mixed cached/not_cacheable - return cached since some files are cached
        return "cached"


@runtime_checkable
class Readable(Protocol):
    """Protocol for file-like objects."""

    def read(self, size: int = -1) -> bytes: ...


@runtime_checkable
class AsyncReadable(Protocol):
    """Protocol for async file-like objects (e.g., anyio.open_file(), aiofiles)."""

    async def read(self, size: int = -1) -> bytes: ...


SyncContent = bytes | str | Readable | Iterator[bytes]
AsyncContent = bytes | str | AsyncReadable | AsyncIterator[bytes]


def _generate_fileset_name() -> str:
    """Generate a unique fileset name using UUID."""
    return f"fileset-{uuid.uuid4().hex[:8]}"


def _matches_glob(filepath: str, pattern: str) -> bool:
    """Match filepath against a glob pattern using pathlib.

    Simple patterns (no /) only match top-level files.
    Path patterns (with /) match the full relative path from the right.

    Examples:
        _matches_glob("train.json", "*.json") -> True
        _matches_glob("subdir/nested.json", "*.json") -> False (nested file)
        _matches_glob("subdir/nested.json", "subdir/*.json") -> True
        _matches_glob("subdir/nested.json", "*/*.json") -> True

    Args:
        filepath: The file path to check (relative path within fileset).
        pattern: Glob pattern to match against.

    Returns:
        True if the filepath matches the pattern.
    """
    if "/" not in pattern:
        # Simple pattern - only matches top-level files
        return "/" not in filepath and PurePath(filepath).match(pattern)
    # Path pattern - match from the right
    return PurePath(filepath).match(pattern)


class FilesetsSubResource:
    """Fileset CRUD operations (create, retrieve, update, list, delete).

    Wraps ``FilesClient`` methods with higher-level convenience signatures
    (unwrapped params, ``exist_ok`` support).

    .. deprecated::
        Temporary shim for the ``sdk.files`` fileset interface.
        New code should use ``FilesClient`` directly.
        Once all callers are migrated, this class will be removed.
    """

    def __init__(self, client: FilesClient) -> None:
        self._client = client

    def create(
        self,
        *,
        name: str,
        workspace: str | None = None,
        exist_ok: bool = False,
        description: str | None = None,
        project: str | None = None,
        purpose: FilesetPurpose | None = None,
        metadata: FilesetMetadata | None = None,
        storage: StorageConfig | None = None,
        custom_fields: dict[str, Any] | None = None,
        cache: bool = False,
    ) -> FilesetOutput:
        body = CreateFilesetRequest(
            name=name,
            description=description,
            project=project,
            purpose=purpose or FilesetPurpose.GENERIC,
            metadata=metadata or FilesetMetadata(),
            storage=storage,
            custom_fields=custom_fields or {},
            cache=cache,
        )
        return self._client.create_fileset(workspace=workspace, body=body, exist_ok=exist_ok).data()

    def retrieve(self, name: str, *, workspace: str | None = None) -> FilesetOutput:
        return self._client.get_fileset(workspace=workspace, name=name).data()

    def update(
        self,
        name: str,
        *,
        workspace: str | None = None,
        description: str | None = None,
        project: str | None = None,
        purpose: FilesetPurpose | None = None,
        metadata: FilesetMetadata | None = None,
        custom_fields: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> FilesetOutput:
        # Only include explicitly provided fields so exclude_unset works correctly
        kwargs = {
            k: v
            for k, v in dict(
                description=description,
                project=project,
                purpose=purpose,
                metadata=metadata,
                custom_fields=custom_fields,
            ).items()
            if v is not None
        }
        body = UpdateFilesetRequest(**kwargs)
        client = self._client.with_options(timeout=timeout) if timeout is not None else self._client
        return client.update_fileset(workspace=workspace, name=name, body=body).data()

    def list(
        self,
        *,
        workspace: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        filter: str | dict | None = None,
    ) -> NemoPaginatedResponse[FilesetOutput]:
        query_params = {
            k: v
            for k, v in dict(
                page=page,
                page_size=page_size,
                sort=sort,
                filter=filter,
            ).items()
            if v is not None
        }
        return self._client.list_filesets(workspace=workspace, query_params=query_params or None)

    def delete(self, name: str, *, workspace: str | None = None) -> FilesetOutput:
        return self._client.delete_fileset(workspace=workspace, name=name).data()


class AsyncFilesetsSubResource:
    """Async fileset CRUD operations (create, retrieve, update, list, delete).

    Wraps ``AsyncFilesClient`` methods with higher-level convenience signatures
    (unwrapped params, ``exist_ok`` support).

    .. deprecated::
        Temporary shim for the ``sdk.files`` fileset interface.
        New code should use ``AsyncFilesClient`` directly.
        Once all callers are migrated, this class will be removed.
    """

    def __init__(self, client: AsyncFilesClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        name: str,
        workspace: str | None = None,
        exist_ok: bool = False,
        description: str | None = None,
        project: str | None = None,
        purpose: FilesetPurpose | None = None,
        metadata: FilesetMetadata | None = None,
        storage: StorageConfig | None = None,
        custom_fields: dict[str, Any] | None = None,
        cache: bool = False,
    ) -> FilesetOutput:
        body = CreateFilesetRequest(
            name=name,
            description=description,
            project=project,
            purpose=purpose or FilesetPurpose.GENERIC,
            metadata=metadata or FilesetMetadata(),
            storage=storage,
            custom_fields=custom_fields or {},
            cache=cache,
        )
        return (await self._client.create_fileset(workspace=workspace, body=body, exist_ok=exist_ok)).data()

    async def retrieve(self, name: str, *, workspace: str | None = None) -> FilesetOutput:
        return (await self._client.get_fileset(workspace=workspace, name=name)).data()

    async def update(
        self,
        name: str,
        *,
        workspace: str | None = None,
        description: str | None = None,
        project: str | None = None,
        purpose: FilesetPurpose | None = None,
        metadata: FilesetMetadata | None = None,
        custom_fields: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> FilesetOutput:
        kwargs = {
            k: v
            for k, v in dict(
                description=description,
                project=project,
                purpose=purpose,
                metadata=metadata,
                custom_fields=custom_fields,
            ).items()
            if v is not None
        }
        body = UpdateFilesetRequest(**kwargs)
        client = self._client.with_options(timeout=timeout) if timeout is not None else self._client
        return (await client.update_fileset(workspace=workspace, name=name, body=body)).data()

    async def list(
        self,
        *,
        workspace: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        filter: str | dict | None = None,
    ) -> AsyncNemoPaginatedResponse[FilesetOutput]:
        query_params = {
            k: v
            for k, v in dict(
                page=page,
                page_size=page_size,
                sort=sort,
                filter=filter,
            ).items()
            if v is not None
        }
        return await self._client.list_filesets(workspace=workspace, query_params=query_params or None)

    async def delete(self, name: str, *, workspace: str | None = None) -> FilesetOutput:
        return (await self._client.delete_fileset(workspace=workspace, name=name)).data()


class FilesResource:
    """FilesResource with high-level file operations.

    Provides convenient methods for uploading, downloading, and listing files.
    For fsspec filesystem access, use ``resource.fsspec``.
    """

    def __init__(self, client) -> None:
        from nemo_platform_plugin.client.adapter import client_from_platform

        self._client = client_from_platform(client, _RemappingFilesClient)

    @cached_property
    def filesets(self) -> FilesetsSubResource:
        """Access fileset CRUD operations (create, retrieve, update, list, delete)."""
        return FilesetsSubResource(self._client)

    @cached_property
    def fsspec(self) -> FilesetFileSystem:
        """Access the underlying fsspec filesystem."""
        return FilesetFileSystem(client=self._client)

    def _ensure_fileset_exists(self, workspace: str, fileset: str) -> None:
        """Create fileset if it doesn't exist (idempotent)."""
        self.filesets.create(name=fileset, workspace=workspace, exist_ok=True)

    def download(
        self,
        *,
        remote_path: str | list[str] = "",
        local_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
        callback: Callback | None = None,
        max_workers: int | None = None,
    ) -> None:
        """Download files from a fileset to a local path.

        Args:
            remote_path: Path(s) within the fileset to download. Can be:
                - A single path (str): Full path (e.g., "workspace/fileset#data/"),
                  relative path (e.g., "data/"), or glob pattern (e.g., "*.json").
                - A list of paths (list[str]): Multiple specific file paths to download.
                  When using a list, fileset and workspace must be provided explicitly.
                Defaults to "" (root of fileset).
            local_path: Local destination path (directory).
            fileset: Fileset name. If not provided, inferred from remote_path (str only).
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.
            callback: Optional progress callback (e.g., RichProgressCallback).
            max_workers: Maximum number of concurrent file transfers.

        Examples:
            # Explicit fileset/workspace
            >>> sdk.files.download(
            ...     fileset="my-fileset",
            ...     workspace="default",
            ...     remote_path="data/",
            ...     local_path="./downloads/"
            ... )

            # Inferred from path (with workspace)
            >>> sdk.files.download(
            ...     remote_path="default/my-fileset#data/",
            ...     local_path="./downloads/"
            ... )

            # Inferred from path (workspace from SDK default)
            >>> sdk.files.download(
            ...     remote_path="my-fileset#data/",
            ...     local_path="./downloads/"
            ... )

            # Download files matching a glob pattern
            >>> sdk.files.download(
            ...     fileset="my-fileset",
            ...     remote_path="*.json",
            ...     local_path="./downloads/"
            ... )

            # Download files matching a pattern in a subdirectory
            >>> sdk.files.download(
            ...     fileset="my-fileset",
            ...     remote_path="data/*.jsonl",
            ...     local_path="./downloads/"
            ... )

            # Download a list of specific files
            >>> sdk.files.download(
            ...     fileset="my-fileset",
            ...     remote_path=["config.json", "tokenizer.json", "vocab.txt"],
            ...     local_path="./downloads/"
            ... )

            # With progress callback
            >>> from nemo_platform.filesets import RichProgressCallback
            >>> with RichProgressCallback(description="Downloading") as cb:
            ...     sdk.files.download(
            ...         remote_path="my-fileset#",
            ...         local_path="./",
            ...         callback=cb
            ...     )
        """
        # Handle list of paths
        if isinstance(remote_path, list):
            if not remote_path:
                return
            ws = workspace or self._client.workspace
            if fileset is None:
                raise ValueError("fileset must be provided when remote_path is a list.")
            if ws is None:
                raise ValueError("workspace must be provided when remote_path is a list.")
            # Build list of (remote, local) path pairs preserving directory structure
            rpaths = [build_fileset_ref(p, workspace=ws, fileset=fileset) for p in remote_path]
            lpaths = [str(PurePath(local_path) / p) for p in remote_path]
            kwargs: dict = {"rpath": rpaths, "lpath": lpaths, "batch_size": max_workers}
            if callback is not None:
                kwargs["callback"] = callback
            self.fsspec.get(**kwargs)
            return

        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        # Handle glob patterns by expanding to list of files first
        if has_magic(path):
            matching_files = self.list(remote_path=path, fileset=fileset, workspace=ws)
            if not matching_files.data:
                return
            # Build list of (remote, local) path pairs preserving directory structure
            rpaths = [build_fileset_ref(f.path, workspace=ws, fileset=fileset) for f in matching_files.data]
            lpaths = [str(PurePath(local_path) / f.path) for f in matching_files.data]
            kwargs = {"rpath": rpaths, "lpath": lpaths, "batch_size": max_workers}
            if callback is not None:
                kwargs["callback"] = callback
            self.fsspec.get(**kwargs)
        else:
            fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
            kwargs = {"rpath": fileset_ref, "lpath": local_path, "recursive": True, "batch_size": max_workers}
            if callback is not None:
                kwargs["callback"] = callback
            self.fsspec.get(**kwargs)

    def upload(
        self,
        *,
        local_path: str,
        remote_path: str = "",
        fileset: str | None = None,
        workspace: str | None = None,
        callback: Callback | None = None,
        max_workers: int | None = None,
        fileset_auto_create: bool = False,
    ) -> FilesetOutput:
        """Upload files from a local path to a fileset.

        Args:
            local_path: Local source path (file or directory).
            remote_path: Path within the fileset to upload to. Can be a full path
                (e.g., "workspace/fileset#data/" or "fileset#data/") if fileset is not provided,
                or a relative path (e.g., "data/") if fileset is provided.
                Defaults to "" (root of fileset).
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.
            callback: Optional progress callback (e.g., RichProgressCallback).
            max_workers: Maximum number of concurrent file transfers.
            fileset_auto_create: If True, create the fileset if it doesn't exist.
                When no fileset is specified (neither as param nor in remote_path),
                a unique name is generated (e.g., "fileset-a1b2c3d4").

        Returns:
            FilesetOutput: The fileset that was uploaded to. Check ``fileset.name`` to see
                the generated name when using fileset_auto_create without specifying
                a fileset.

        Examples:
            # Explicit fileset/workspace
            >>> sdk.files.upload(
            ...     fileset="my-fileset",
            ...     workspace="default",
            ...     local_path="./data/",
            ...     remote_path="uploads/"
            ... )

            # Inferred from path
            >>> sdk.files.upload(
            ...     local_path="./file.txt",
            ...     remote_path="default/my-fileset#file.txt"
            ... )

            # With workspace from SDK default
            >>> sdk.files.upload(
            ...     local_path="./file.txt",
            ...     remote_path="my-fileset#file.txt"
            ... )

            # Auto-create fileset with specified name
            >>> fileset = sdk.files.upload(
            ...     local_path="./data/",
            ...     fileset="new-fileset",
            ...     fileset_auto_create=True
            ... )
            >>> print(f"Uploaded to: {fileset.name}")

            # Auto-create fileset with generated name
            >>> fileset = sdk.files.upload(
            ...     local_path="./data/",
            ...     fileset_auto_create=True
            ... )
            >>> print(f"Uploaded to: {fileset.name}")  # e.g., "fileset-a1b2c3d4"
        """
        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            if fileset_auto_create:
                fileset = _generate_fileset_name()
            else:
                raise ValueError(
                    "Fileset must be specified either as a parameter or in the remote_path when fileset_auto_create is False."
                )

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        if fileset_auto_create:
            self._ensure_fileset_exists(ws, fileset)

        kwargs: dict = {"lpath": local_path, "rpath": fileset_ref, "recursive": True, "batch_size": max_workers}
        if callback is not None:
            kwargs["callback"] = callback
        self.fsspec.put(**kwargs)

        return self.filesets.retrieve(name=fileset, workspace=ws)

    def upload_content(
        self,
        *,
        content: SyncContent,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
        fileset_auto_create: bool = False,
    ) -> FilesetOutput:
        """Upload in-memory content to a fileset.

        Args:
            content: Content to upload. Can be:
                - bytes: Raw byte content
                - str: Text content (will be UTF-8 encoded)
                - BinaryIO: File-like object (e.g., BytesIO, open file)
                - Iterator[bytes]: Generator or iterator yielding byte chunks
            remote_path: Destination path within the fileset.
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, uses client default.
            fileset_auto_create: If True, create the fileset if it doesn't exist.
                When no fileset is specified (neither as param nor in remote_path),
                a unique name is generated (e.g., "fileset-a1b2c3d4").

        Returns:
            FilesetOutput: The fileset that was uploaded to. Check ``fileset.name`` to see
                the generated name when using fileset_auto_create without specifying
                a fileset.

        Examples:
            # Upload bytes
            >>> sdk.files.upload_content(
            ...     content=b"Hello, World!",
            ...     remote_path="message.txt",
            ...     fileset="my-fileset",
            ... )

            # Upload string (auto UTF-8 encoded)
            >>> sdk.files.upload_content(
            ...     content='{"key": "value"}',
            ...     remote_path="config.json",
            ...     fileset="my-fileset",
            ... )

            # Upload from BytesIO
            >>> from io import BytesIO
            >>> sdk.files.upload_content(
            ...     content=BytesIO(b"content"),
            ...     remote_path="data.bin",
            ...     fileset="my-fileset",
            ... )

            # Auto-create fileset with specified name
            >>> fileset = sdk.files.upload_content(
            ...     content=b"content",
            ...     remote_path="file.txt",
            ...     fileset="new-fileset",
            ...     fileset_auto_create=True,
            ... )
            >>> print(f"Uploaded to: {fileset.name}")

            # Auto-create fileset with generated name
            >>> fileset = sdk.files.upload_content(
            ...     content=b"content",
            ...     remote_path="file.txt",
            ...     fileset_auto_create=True,
            ... )
            >>> print(f"Uploaded to: {fileset.name}")  # e.g., "fileset-a1b2c3d4"
        """
        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            if fileset_auto_create:
                fileset = _generate_fileset_name()
            else:
                raise ValueError(
                    "Fileset must be specified either as a parameter or in the remote_path when fileset_auto_create is False."
                )

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        if fileset_auto_create:
            self._ensure_fileset_exists(ws, fileset)

        match content:
            case str():
                self.fsspec.pipe(fileset_ref, content.encode("utf-8"))
            case bytes():
                self.fsspec.pipe(fileset_ref, content)
            case Readable():
                self.fsspec.pipe(fileset_ref, content.read())
            case content if hasattr(content, "__next__"):
                self.fsspec.pipe_stream(fileset_ref, content)
            case _:
                raise TypeError(f"Unsupported content type: {type(content)}")

        return self.filesets.retrieve(name=fileset, workspace=ws)

    def download_content(
        self,
        *,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> bytes:
        """Download a file's content from a fileset.

        Args:
            remote_path: Path of the file within the fileset.
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, uses client default.

        Returns:
            bytes: The file content.

        Examples:
            # Load JSON (most common use case)
            >>> data = json.loads(sdk.files.download_content(
            ...     remote_path="config.json",
            ...     fileset="my-fileset",
            ... ))

            # Get text content
            >>> text = sdk.files.download_content(
            ...     remote_path="readme.txt",
            ...     fileset="my-fileset",
            ... ).decode("utf-8")

            # Get binary content
            >>> content = sdk.files.download_content(
            ...     remote_path="model.bin",
            ...     fileset="my-fileset",
            ... )
        """
        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        return self.fsspec.cat(fileset_ref)

    def list(
        self,
        *,
        remote_path: str = "",
        fileset: str | None = None,
        workspace: str | None = None,
        include_cache_status: bool = False,
    ) -> ListFilesResponse:
        """List all files in a fileset path (recursive), with optional glob pattern support.

        Args:
            remote_path: Path within the fileset to list. Can be a full path
                (e.g., "workspace/fileset#data/" or "fileset#data/") if fileset is not provided,
                or a relative path (e.g., "data/") if fileset is provided.
                Supports glob patterns (*, ?, []) for filtering files.
                Defaults to "" (root of fileset).
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.
            include_cache_status: Check and return cache status for each file.
                When False (default), external storage files return None for cache_status.

        Returns:
            ListFilesResponse with data (list of FilesetFileOutput) and cache_status property.

        Examples:
            # List all files in a fileset
            >>> response = sdk.files.list(fileset="my-fileset")
            >>> for f in response.data:
            ...     print(f"{f.path}: {f.size} bytes")

            # List files in a subdirectory
            >>> sdk.files.list(
            ...     fileset="my-fileset",
            ...     remote_path="data/"
            ... )

            # List files matching a glob pattern
            >>> sdk.files.list(
            ...     fileset="my-fileset",
            ...     remote_path="*.json"
            ... )

            # List files matching a pattern in a subdirectory
            >>> sdk.files.list(
            ...     fileset="my-fileset",
            ...     remote_path="data/*.jsonl"
            ... )

            # Inferred from path
            >>> sdk.files.list(remote_path="my-fileset#data/")

            # Check cache status for external storage
            >>> response = sdk.files.list(fileset="my-fileset", include_cache_status=True)
            >>> print(f"Cache status: {response.cache_status}")
            >>> for f in response.data:
            ...     print(f"{f.path}: {f.cache_status}")
        """
        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        # For glob patterns, list all files then filter client-side
        # For path prefixes, the API handles filtering server-side
        api_path = None if has_magic(path) else (path or None)

        query_params = {}
        if api_path is not None:
            query_params["path"] = api_path
        if include_cache_status:
            query_params["include_cache_status"] = True

        response = self._client.list_files(
            workspace=ws,
            name=fileset,
            query_params=query_params or None,
        )
        response = response.data()
        files = list(response.data)

        # Apply glob filtering if needed
        if has_magic(path):
            files = [f for f in files if _matches_glob(f.path, path)]
        return ListFilesResponse(data=files)

    def delete(
        self,
        *,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> None:
        """Delete a file from a fileset.

        Args:
            remote_path: Path of the file to delete. Can be a full path
                (e.g., "workspace/fileset#data/file.txt") if fileset is not provided,
                or a relative path (e.g., "data/file.txt") if fileset is provided.
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.

        Examples:
            # Delete a file with explicit fileset
            >>> sdk.files.delete(
            ...     fileset="my-fileset",
            ...     remote_path="data/old-file.txt"
            ... )

            # Delete using full path
            >>> sdk.files.delete(remote_path="my-fileset#data/old-file.txt")
        """
        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        self.fsspec.rm(fileset_ref)


class AsyncFilesResource:
    """Async FilesResource with high-level file operations.

    Provides convenient methods for uploading, downloading, and listing files.
    For fsspec filesystem access, use ``resource.fsspec``.
    """

    def __init__(self, client) -> None:
        from nemo_platform_plugin.client.adapter import client_from_platform

        self._client = client_from_platform(client, _RemappingAsyncFilesClient)

    @cached_property
    def filesets(self) -> AsyncFilesetsSubResource:
        """Access fileset CRUD operations (create, retrieve, update, list, delete)."""
        return AsyncFilesetsSubResource(self._client)

    @cached_property
    def fsspec(self) -> FilesetFileSystem:
        """Access the underlying fsspec filesystem."""
        return FilesetFileSystem(client=self._client)

    async def _ensure_fileset_exists(self, workspace: str, fileset: str) -> None:
        """Create fileset if it doesn't exist (idempotent)."""
        await self.filesets.create(name=fileset, workspace=workspace, exist_ok=True)

    async def download(
        self,
        *,
        remote_path: str | list[str] = "",
        local_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
        callback: Callback | None = None,
        max_workers: int | None = None,
    ) -> None:
        """Download files from a fileset to a local path (async).

        Args:
            remote_path: Path(s) within the fileset to download. Can be:
                - A single path (str): Full path (e.g., "workspace/fileset#data/"),
                  relative path (e.g., "data/"), or glob pattern (e.g., "*.json").
                - A list of paths (list[str]): Multiple specific file paths to download.
                  When using a list, fileset and workspace must be provided explicitly.
                Defaults to "" (root of fileset).
            local_path: Local destination path (directory).
            fileset: Fileset name. If not provided, inferred from remote_path (str only).
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.
            callback: Optional progress callback (e.g., RichProgressCallback).
            max_workers: Maximum number of concurrent file transfers.

        Examples:
            # Explicit fileset/workspace
            >>> await sdk.files.download(
            ...     fileset="my-fileset",
            ...     workspace="default",
            ...     remote_path="data/",
            ...     local_path="./downloads/"
            ... )

            # Inferred from path
            >>> await sdk.files.download(
            ...     remote_path="default/my-fileset#data/",
            ...     local_path="./downloads/"
            ... )

            # Download files matching a glob pattern
            >>> await sdk.files.download(
            ...     fileset="my-fileset",
            ...     remote_path="*.json",
            ...     local_path="./downloads/"
            ... )

            # Download files matching a pattern in a subdirectory
            >>> await sdk.files.download(
            ...     fileset="my-fileset",
            ...     remote_path="data/*.jsonl",
            ...     local_path="./downloads/"
            ... )

            # Download a list of specific files
            >>> await sdk.files.download(
            ...     fileset="my-fileset",
            ...     remote_path=["config.json", "tokenizer.json", "vocab.txt"],
            ...     local_path="./downloads/"
            ... )
        """
        # Handle list of paths
        if isinstance(remote_path, list):
            if not remote_path:
                return
            ws = workspace or self._client.workspace
            if fileset is None:
                raise ValueError("fileset must be provided when remote_path is a list.")
            if ws is None:
                raise ValueError("workspace must be provided when remote_path is a list.")
            # Build list of (remote, local) path pairs preserving directory structure
            rpaths = [build_fileset_ref(p, workspace=ws, fileset=fileset) for p in remote_path]
            lpaths = [str(PurePath(local_path) / p) for p in remote_path]
            kwargs: dict = {"rpath": rpaths, "lpath": lpaths, "batch_size": max_workers}
            if callback is not None:
                kwargs["callback"] = callback
            await self.fsspec._get(**kwargs)
            return

        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        # Handle glob patterns by expanding to list of files first
        if has_magic(path):
            matching_files = await self.list(remote_path=path, fileset=fileset, workspace=ws)
            if not matching_files.data:
                return
            # Build list of (remote, local) path pairs preserving directory structure
            rpaths = [build_fileset_ref(f.path, workspace=ws, fileset=fileset) for f in matching_files.data]
            lpaths = [str(PurePath(local_path) / f.path) for f in matching_files.data]
            kwargs = {"rpath": rpaths, "lpath": lpaths, "batch_size": max_workers}
            if callback is not None:
                kwargs["callback"] = callback
            await self.fsspec._get(**kwargs)
        else:
            fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
            kwargs = {"rpath": fileset_ref, "lpath": local_path, "recursive": True, "batch_size": max_workers}
            if callback is not None:
                kwargs["callback"] = callback
            await self.fsspec._get(**kwargs)

    async def upload(
        self,
        *,
        local_path: str,
        remote_path: str = "",
        fileset: str | None = None,
        workspace: str | None = None,
        callback: Callback | None = None,
        max_workers: int | None = None,
        fileset_auto_create: bool = False,
    ) -> FilesetOutput:
        """Upload files from a local path to a fileset (async).

        Args:
            local_path: Local source path (file or directory).
            remote_path: Path within the fileset to upload to. Can be a full path
                (e.g., "workspace/fileset#data/" or "fileset#data/") if fileset is not provided,
                or a relative path (e.g., "data/") if fileset is provided.
                Defaults to "" (root of fileset).
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.
            callback: Optional progress callback (e.g., RichProgressCallback).
            max_workers: Maximum number of concurrent file transfers.
            fileset_auto_create: If True, create the fileset if it doesn't exist.
                When no fileset is specified (neither as param nor in remote_path),
                a unique name is generated (e.g., "fileset-a1b2c3d4").

        Returns:
            FilesetOutput: The fileset that was uploaded to. Check ``fileset.name`` to see
                the generated name when using fileset_auto_create without specifying
                a fileset.

        Examples:
            # Explicit fileset/workspace
            >>> await sdk.files.upload(
            ...     fileset="my-fileset",
            ...     workspace="default",
            ...     local_path="./data/",
            ...     remote_path="uploads/"
            ... )

            # Inferred from path
            >>> await sdk.files.upload(
            ...     local_path="./file.txt",
            ...     remote_path="default/my-fileset#file.txt"
            ... )

            # Auto-create fileset with specified name
            >>> fileset = await sdk.files.upload(
            ...     local_path="./data/",
            ...     fileset="new-fileset",
            ...     fileset_auto_create=True
            ... )
            >>> print(f"Uploaded to: {fileset.name}")

            # Auto-create fileset with generated name
            >>> fileset = await sdk.files.upload(
            ...     local_path="./data/",
            ...     fileset_auto_create=True
            ... )
            >>> print(f"Uploaded to: {fileset.name}")  # e.g., "fileset-a1b2c3d4"
        """
        ws, path_fileset, path = parse_fileset_path(
            remote_path,
            workspace_fallback=workspace or self._client.workspace,
        )
        fileset = fileset or path_fileset

        if fileset is None:
            if fileset_auto_create:
                fileset = _generate_fileset_name()
            else:
                raise ValueError(
                    "Fileset must be specified either as a parameter or in the remote_path when fileset_auto_create is False."
                )

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        if fileset_auto_create:
            await self._ensure_fileset_exists(ws, fileset)

        kwargs: dict = {"lpath": local_path, "rpath": fileset_ref, "recursive": True, "batch_size": max_workers}
        if callback is not None:
            kwargs["callback"] = callback
        await self.fsspec._put(**kwargs)

        return await self.filesets.retrieve(name=fileset, workspace=ws)

    async def upload_content(
        self,
        *,
        content: AsyncContent,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
        fileset_auto_create: bool = False,
    ) -> FilesetOutput:
        """Upload in-memory data to a fileset (async).

        Args:
            content: Content to upload. Can be:
                - bytes: Raw byte content
                - str: Text content (will be UTF-8 encoded)
                - AsyncReadable: Async file-like object (e.g., anyio.open_file(), aiofiles)
                - AsyncIterator[bytes]: Async iterator yielding byte chunks (streamed)
            remote_path: Destination path within the fileset.
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, uses client default.
            fileset_auto_create: If True, create the fileset if it doesn't exist.
                When no fileset is specified (neither as param nor in remote_path),
                a unique name is generated (e.g., "fileset-a1b2c3d4").

        Returns:
            FilesetOutput: The fileset that was uploaded to. Check ``fileset.name`` to see
                the generated name when using fileset_auto_create without specifying
                a fileset.

        Examples:
            # Upload bytes
            >>> await sdk.files.upload_content(
            ...     content=b"Hello, World!",
            ...     remote_path="message.txt",
            ...     fileset="my-fileset",
            ... )

            # Upload string (auto UTF-8 encoded)
            >>> await sdk.files.upload_content(
            ...     content='{"key": "value"}',
            ...     remote_path="config.json",
            ...     fileset="my-fileset",
            ... )

            # Upload from async file (anyio/aiofiles)
            >>> async with await anyio.open_file("data.bin", "rb") as f:
            ...     await sdk.files.upload_content(
            ...         content=f,
            ...         remote_path="data.bin",
            ...         fileset="my-fileset",
            ...     )

            # Auto-create fileset with specified name
            >>> fileset = await sdk.files.upload_content(
            ...     content=b"content",
            ...     remote_path="file.txt",
            ...     fileset="new-fileset",
            ...     fileset_auto_create=True,
            ... )
            >>> print(f"Uploaded to: {fileset.name}")

            # Auto-create fileset with generated name
            >>> fileset = await sdk.files.upload_content(
            ...     content=b"content",
            ...     remote_path="file.txt",
            ...     fileset_auto_create=True,
            ... )
            >>> print(f"Uploaded to: {fileset.name}")  # e.g., "fileset-a1b2c3d4"
        """
        ws, path_fileset, path = parse_fileset_path(remote_path, workspace_fallback=workspace or self._client.workspace)
        fileset = fileset or path_fileset

        if fileset is None:
            if fileset_auto_create:
                fileset = _generate_fileset_name()
            else:
                raise ValueError(
                    "Fileset must be specified either as a parameter or in the remote_path when fileset_auto_create is False."
                )

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        if fileset_auto_create:
            await self._ensure_fileset_exists(ws, fileset)

        async def _read_chunks(f: AsyncReadable, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        match content:
            case str():
                await self.fsspec._pipe_file(fileset_ref, content.encode("utf-8"))
            case bytes():
                await self.fsspec._pipe_file(fileset_ref, content)
            case AsyncReadable():
                await self.fsspec._pipe_stream(fileset_ref, _read_chunks(content))
            case content if hasattr(content, "__anext__"):
                await self.fsspec._pipe_stream(fileset_ref, content)
            case _:
                raise TypeError(f"Unsupported content type: {type(content)}")

        return await self.filesets.retrieve(name=fileset, workspace=ws)

    async def download_content(
        self,
        *,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> bytes:
        """Download a file's content from a fileset (async).

        Args:
            remote_path: Path of the file within the fileset.
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, uses client default.

        Returns:
            bytes: The file content.

        Examples:
            # Load JSON
            >>> content = await sdk.files.download_content(
            ...     remote_path="config.json",
            ...     fileset="my-fileset",
            ... )
            >>> data = json.loads(content)

            # Get text content
            >>> text = (await sdk.files.download_content(
            ...     remote_path="readme.txt",
            ...     fileset="my-fileset",
            ... )).decode("utf-8")
        """
        ws, path_fileset, path = parse_fileset_path(remote_path, workspace_fallback=workspace or self._client.workspace)
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        return await self.fsspec._cat_file(fileset_ref)

    async def list(
        self,
        *,
        remote_path: str = "",
        fileset: str | None = None,
        workspace: str | None = None,
        include_cache_status: bool = False,
    ) -> ListFilesResponse:
        """List all files in a fileset path (recursive, async), with optional glob pattern support.

        Args:
            remote_path: Path within the fileset to list. Can be a full path
                (e.g., "workspace/fileset#data/" or "fileset#data/") if fileset is not provided,
                or a relative path (e.g., "data/") if fileset is provided.
                Supports glob patterns (*, ?, []) for filtering files.
                Defaults to "" (root of fileset).
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.
            include_cache_status: Check and return cache status for each file.
                When False (default), external storage files return None for cache_status.

        Returns:
            ListFilesResponse with data (list of FilesetFileOutput) and cache_status property.

        Examples:
            # List all files in a fileset
            >>> response = await sdk.files.list(fileset="my-fileset")
            >>> for f in response.data:
            ...     print(f"{f.path}: {f.size} bytes")

            # List files in a subdirectory
            >>> await sdk.files.list(
            ...     fileset="my-fileset",
            ...     remote_path="data/"
            ... )

            # List files matching a glob pattern
            >>> await sdk.files.list(
            ...     fileset="my-fileset",
            ...     remote_path="*.json"
            ... )

            # List files matching a pattern in a subdirectory
            >>> await sdk.files.list(
            ...     fileset="my-fileset",
            ...     remote_path="data/*.jsonl"
            ... )

            # Inferred from path
            >>> await sdk.files.list(remote_path="my-fileset#data/")

            # Check cache status for external storage
            >>> response = await sdk.files.list(fileset="my-fileset", include_cache_status=True)
            >>> print(f"Cache status: {response.cache_status}")
            >>> for f in response.data:
            ...     print(f"{f.path}: {f.cache_status}")
        """
        ws, path_fileset, path = parse_fileset_path(remote_path, workspace_fallback=workspace or self._client.workspace)
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        # For glob patterns, list all files then filter client-side
        # For path prefixes, the API handles filtering server-side
        api_path = None if has_magic(path) else (path or None)

        query_params = {}
        if api_path is not None:
            query_params["path"] = api_path
        if include_cache_status:
            query_params["include_cache_status"] = True

        response = await self._client.list_files(
            workspace=ws,
            name=fileset,
            query_params=query_params or None,
        )
        response = response.data()
        files = list(response.data)

        # Apply glob filtering if needed
        if has_magic(path):
            files = [f for f in files if _matches_glob(f.path, path)]
        return ListFilesResponse(data=files)

    async def delete(
        self,
        *,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> None:
        """Delete a file from a fileset (async).

        Args:
            remote_path: Path of the file to delete. Can be a full path
                (e.g., "workspace/fileset#data/file.txt") if fileset is not provided,
                or a relative path (e.g., "data/file.txt") if fileset is provided.
            fileset: Fileset name. If not provided, inferred from remote_path.
            workspace: Workspace name. If not provided, inferred from remote_path
                or uses the client's default workspace.

        Examples:
            # Delete a file with explicit fileset
            >>> await sdk.files.delete(
            ...     fileset="my-fileset",
            ...     remote_path="data/old-file.txt"
            ... )

            # Delete using full path
            >>> await sdk.files.delete(remote_path="my-fileset#data/old-file.txt")
        """
        ws, path_fileset, path = parse_fileset_path(remote_path, workspace_fallback=workspace or self._client.workspace)
        fileset = fileset or path_fileset

        if fileset is None:
            raise ValueError("Fileset must be specified either as a parameter or in the remote_path.")

        fileset_ref = build_fileset_ref(path, workspace=ws, fileset=fileset)
        await self.fsspec._rm(fileset_ref)
