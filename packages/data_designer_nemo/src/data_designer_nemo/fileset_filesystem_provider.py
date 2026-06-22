# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path, PurePosixPath

from data_designer.engine.resources.seed_reader import (
    FileSystemProvider,
    LocalFileSystemProvider,
    SeedReaderConfigError,
    SeedReaderError,
    SeedReaderFileSystemContext,
)
from data_designer_nemo.sdk_translation import async_to_sync_sdk
from fsspec.implementations.dirfs import DirFileSystem
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.filesets import FilesetFileSystem, FilesetPathError, build_fileset_ref, parse_fileset_ref
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import AsyncFilesClient, FilesClient


class _FilesetDirFileSystem(DirFileSystem):
    """DirFileSystem that handles FilesetFileSystem's '#' path separator.

    FilesetFileSystem returns paths using '#' to separate the fileset name from
    the file path (e.g. "ws/fs#data.parquet"). Standard DirFileSystem._relpath
    builds its strip-prefix with '/' (e.g. "ws/fs/"), so the startswith check
    fails for fileset-root paths. For subdirectory roots (e.g. "ws/fs#subdir"),
    files use '/' after '#' and the standard logic already works; the '#' branch
    below is a no-op in that case.

    All methods besides _relpath are inherited from DirFileSystem unchanged, so
    this remains a complete AbstractFileSystem implementation.
    """

    def _relpath(self, path: str | list) -> str | list:
        if isinstance(path, list):
            return [self._relpath(p) for p in path]
        if not self.path:
            return path
        if path == self.path:
            return ""
        for sep in ("#", "/"):
            prefix = self.path + sep
            if path.startswith(prefix):
                return path[len(prefix) :]
        raise AssertionError(f"Path {path!r} does not start with root {self.path!r}")


class FilesetFileSystemProvider:
    """Filesystem provider that roots directory-style seed readers in a fileset."""

    def __init__(
        self,
        sdk: NeMoPlatform | AsyncNeMoPlatform,
        *,
        workspace: str,
        validated_roots: set[str] | None = None,
    ) -> None:
        self._async_sdk: AsyncNeMoPlatform | None = sdk if isinstance(sdk, AsyncNeMoPlatform) else None
        if isinstance(sdk, AsyncNeMoPlatform):
            sdk = async_to_sync_sdk(sdk)
        self._sdk = sdk
        self._files_client: FilesClient | None = None
        self._async_files_client: AsyncFilesClient | None = None
        self._workspace = workspace
        self._validated_roots = validated_roots or set()

    def create_context(self, *, runtime_path: str) -> SeedReaderFileSystemContext:
        root = self._canonical_root(runtime_path)
        fs = self._make_filesystem()
        rooted_fs = _FilesetDirFileSystem(path=root, fs=fs)
        return SeedReaderFileSystemContext(fs=rooted_fs, root_path=PurePosixPath(root))

    def ensure_root_exists(self, *, runtime_path: str) -> None:
        workspace, fileset, fragment = self._parse(runtime_path)
        root = build_fileset_ref(fragment, workspace=workspace, fileset=fileset)
        if root in self._validated_roots:
            return

        fs = self._make_filesystem()
        if fs.exists(root):
            self._validated_roots.add(root)
            return

        fileset_root = build_fileset_ref("", workspace=workspace, fileset=fileset)
        fully_qualified_fileset_name = f"{workspace}/{fileset}"
        if not fs.exists(fileset_root):
            raise SeedReaderConfigError(f"🛑 Fileset {fully_qualified_fileset_name!r} not found.")
        raise SeedReaderConfigError(f"🛑 Path {fragment!r} not found in fileset {fully_qualified_fileset_name!r}.")

    def _canonical_root(self, runtime_path: str) -> str:
        workspace, fileset, fragment = self._parse(runtime_path)
        return build_fileset_ref(fragment, workspace=workspace, fileset=fileset)

    def _make_filesystem(self) -> FilesetFileSystem:
        return FilesetFileSystem(client=self._get_files_client(), async_client=self._get_async_files_client())

    def _get_files_client(self) -> FilesClient:
        if self._files_client is not None:
            return self._files_client

        self._files_client = client_from_platform(self._sdk, FilesClient)

        return self._files_client

    def _get_async_files_client(self) -> AsyncFilesClient | None:
        if self._async_sdk is None:
            return None
        if self._async_files_client is None:
            self._async_files_client = client_from_platform(self._async_sdk, AsyncFilesClient)
        return self._async_files_client

    def _parse(self, runtime_path: str) -> tuple[str, str, str]:
        try:
            return parse_fileset_ref(runtime_path, workspace_fallback=self._workspace)
        except FilesetPathError as error:
            raise SeedReaderError(f"🛑 Invalid fileset seed source path {runtime_path!r}: {error}") from error


class HybridFileSystemProvider:
    """Filesystem provider that resolves a seed path against local disk first, then a fileset.

    In local mode a directory-style seed source may point at either a directory on
    the local filesystem or a NeMo Platform fileset, and the engine only lets us
    inject a single provider per seed reader. We route per path: if the path
    resolves to an existing local directory we serve it from disk, otherwise we
    treat it as a fileset reference. This mirrors the local-first model-provider
    resolution strategy (locally-defined providers first, Inference Gateway as the
    fallback).
    """

    def __init__(
        self,
        sdk: NeMoPlatform | AsyncNeMoPlatform,
        *,
        workspace: str,
        validated_roots: set[str] | None = None,
    ) -> None:
        self._local = LocalFileSystemProvider()
        self._fileset = FilesetFileSystemProvider(sdk, workspace=workspace, validated_roots=validated_roots)

    def create_context(self, *, runtime_path: str) -> SeedReaderFileSystemContext:
        return self._route(runtime_path).create_context(runtime_path=runtime_path)

    def ensure_root_exists(self, *, runtime_path: str) -> None:
        self._route(runtime_path).ensure_root_exists(runtime_path=runtime_path)

    def _route(self, runtime_path: str) -> FileSystemProvider:
        return self._local if is_local_directory(runtime_path) else self._fileset


def is_local_directory(runtime_path: str) -> bool:
    """Whether a seed path resolves to an existing directory on the local filesystem.

    Shared by ``HybridFileSystemProvider`` routing and local-mode seed validation so
    that eager validation and read-time routing always agree on which backend serves
    a given path.
    """
    try:
        return Path(runtime_path).expanduser().is_dir()
    except (OSError, ValueError, RuntimeError):
        return False
