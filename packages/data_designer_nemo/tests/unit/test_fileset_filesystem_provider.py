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


def test_create_context_roots_reader_in_canonical_fileset_ref() -> None:
    sdk = Mock()
    filesystem = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.make_filesystem", return_value=filesystem) as make_fs:
        filesystem.async_impl = True
        filesystem.asynchronous = False
        context = FilesetFileSystemProvider(sdk, workspace="default").create_context(runtime_path="docs#corpus")

    make_fs.assert_called_once_with(sdk)
    assert str(context.root_path) == "default/docs#corpus"


def test_ensure_root_exists_skips_validated_roots() -> None:
    sdk = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.make_filesystem") as make_fs:
        FilesetFileSystemProvider(
            sdk,
            workspace="default",
            validated_roots={"default/docs#corpus"},
        ).ensure_root_exists(runtime_path="docs#corpus")

    make_fs.assert_not_called()


def test_ensure_root_exists_reports_missing_fileset_path() -> None:
    sdk = Mock()
    filesystem = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.make_filesystem", return_value=filesystem):
        filesystem.exists.side_effect = [False, True]
        provider = FilesetFileSystemProvider(sdk, workspace="default")

        with pytest.raises(SeedReaderConfigError, match="Path 'corpus' not found in fileset 'default/docs'"):
            provider.ensure_root_exists(runtime_path="docs#corpus")

    assert filesystem.exists.call_count == 2


def test_hybrid_routes_existing_local_directory_to_disk(tmp_path: Path) -> None:
    sdk = Mock()
    provider = HybridFileSystemProvider(sdk, workspace="default")

    with patch("data_designer_nemo.fileset_filesystem_provider.make_filesystem") as make_fs:
        context = provider.create_context(runtime_path=str(tmp_path))
        provider.ensure_root_exists(runtime_path=str(tmp_path))

    assert context.root_path == tmp_path.resolve()
    make_fs.assert_not_called()


def test_hybrid_routes_non_local_path_to_fileset() -> None:
    sdk = Mock()
    provider = HybridFileSystemProvider(sdk, workspace="default")
    filesystem = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.make_filesystem", return_value=filesystem) as make_fs:
        filesystem.async_impl = True
        filesystem.asynchronous = False
        context = provider.create_context(runtime_path="docs#corpus")

    make_fs.assert_called_once_with(sdk)
    assert str(context.root_path) == "default/docs#corpus"


def test_hybrid_ensure_root_exists_validates_fileset_for_non_local_path() -> None:
    sdk = Mock()
    provider = HybridFileSystemProvider(sdk, workspace="default")
    filesystem = Mock()

    with patch("data_designer_nemo.fileset_filesystem_provider.make_filesystem", return_value=filesystem):
        filesystem.exists.side_effect = [False, True]

        with pytest.raises(SeedReaderConfigError, match="Path 'corpus' not found in fileset 'default/docs'"):
            provider.ensure_root_exists(runtime_path="docs#corpus")

    assert filesystem.exists.call_count == 2


def test_local_context_wires_hybrid_provider_into_filesystem_readers() -> None:
    readers = LocalDataDesignerContext(Mock(), "default").get_seed_readers()

    fs_readers = [r for r in readers if isinstance(r, DirectorySeedReader | FileContentsSeedReader)]
    assert len(fs_readers) == 2
    assert all(isinstance(r._fs_provider, HybridFileSystemProvider) for r in fs_readers)
