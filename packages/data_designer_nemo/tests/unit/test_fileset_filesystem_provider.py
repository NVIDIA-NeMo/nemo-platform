# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from data_designer.engine.resources.seed_reader import (
    DirectorySeedReader,
    FileContentsSeedReader,
    SeedReaderConfigError,
)
from data_designer_nemo.context import LocalDataDesignerContext
from data_designer_nemo.fileset_filesystem_provider import FilesetFileSystemProvider, HybridFileSystemProvider
from nemo_platform import AsyncNeMoPlatform


def test_create_context_roots_reader_in_canonical_fileset_ref() -> None:
    sdk = Mock()
    files_client = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class:
        with patch("data_designer_nemo.fileset_filesystem_provider.client_from_platform", return_value=files_client):
            fs_class.return_value.async_impl = True
            fs_class.return_value.asynchronous = False
            context = FilesetFileSystemProvider(sdk, workspace="default").create_context(runtime_path="docs#corpus")

    fs_class.assert_called_once_with(client=files_client, async_client=None)
    assert str(context.root_path) == "default/docs#corpus"


def test_create_context_preserves_async_files_client() -> None:
    sdk = Mock(spec=AsyncNeMoPlatform)
    sync_files_client = Mock()
    async_files_client = Mock()

    with (
        patch("data_designer_nemo.fileset_filesystem_provider.async_to_sync_sdk", return_value=Mock()),
        patch(
            "data_designer_nemo.fileset_filesystem_provider.client_from_platform",
            side_effect=[sync_files_client, async_files_client],
        ),
        patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class,
    ):
        fs_class.return_value.async_impl = True
        fs_class.return_value.asynchronous = False
        context = FilesetFileSystemProvider(sdk, workspace="default").create_context(runtime_path="docs#corpus")

    fs_class.assert_called_once_with(client=sync_files_client, async_client=async_files_client)
    assert str(context.root_path) == "default/docs#corpus"


def test_ensure_root_exists_skips_validated_roots() -> None:
    sdk = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class:
        FilesetFileSystemProvider(
            sdk,
            workspace="default",
            validated_roots={"default/docs#corpus"},
        ).ensure_root_exists(runtime_path="docs#corpus")

    fs_class.assert_not_called()


def test_ensure_root_exists_reports_missing_fileset_path() -> None:
    sdk = Mock()
    files_client = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class:
        with patch("data_designer_nemo.fileset_filesystem_provider.client_from_platform", return_value=files_client):
            fs_class.return_value.exists.side_effect = [False, True]
            provider = FilesetFileSystemProvider(sdk, workspace="default")

            with pytest.raises(SeedReaderConfigError, match="Path 'corpus' not found in fileset 'default/docs'"):
                provider.ensure_root_exists(runtime_path="docs#corpus")

    assert fs_class.return_value.exists.call_count == 2


def test_hybrid_routes_existing_local_directory_to_disk(tmp_path: Path) -> None:
    sdk = Mock()
    provider = HybridFileSystemProvider(sdk, workspace="default")

    with patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class:
        context = provider.create_context(runtime_path=str(tmp_path))
        provider.ensure_root_exists(runtime_path=str(tmp_path))

    assert context.root_path == tmp_path.resolve()
    fs_class.assert_not_called()


def test_hybrid_routes_non_local_path_to_fileset() -> None:
    sdk = Mock()
    provider = HybridFileSystemProvider(sdk, workspace="default")
    files_client = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class:
        with patch("data_designer_nemo.fileset_filesystem_provider.client_from_platform", return_value=files_client):
            fs_class.return_value.async_impl = True
            fs_class.return_value.asynchronous = False
            context = provider.create_context(runtime_path="docs#corpus")

    fs_class.assert_called_once_with(client=files_client, async_client=None)
    assert str(context.root_path) == "default/docs#corpus"


def test_hybrid_ensure_root_exists_validates_fileset_for_non_local_path() -> None:
    sdk = Mock()
    provider = HybridFileSystemProvider(sdk, workspace="default")
    files_client = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.FilesetFileSystem") as fs_class:
        with patch("data_designer_nemo.fileset_filesystem_provider.client_from_platform", return_value=files_client):
            fs_class.return_value.exists.side_effect = [False, True]

            with pytest.raises(SeedReaderConfigError, match="Path 'corpus' not found in fileset 'default/docs'"):
                provider.ensure_root_exists(runtime_path="docs#corpus")

    assert fs_class.return_value.exists.call_count == 2


def test_local_context_wires_hybrid_provider_into_filesystem_readers() -> None:
    readers = LocalDataDesignerContext(Mock(), "default").get_seed_readers()

    fs_readers = [r for r in readers if isinstance(r, DirectorySeedReader | FileContentsSeedReader)]
    assert len(fs_readers) == 2
    assert all(isinstance(r._fs_provider, HybridFileSystemProvider) for r in fs_readers)
