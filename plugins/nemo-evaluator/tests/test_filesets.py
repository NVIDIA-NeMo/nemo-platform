# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for evaluator FilesetRef helpers."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from nemo_evaluator.filesets import FilesetRef, download_dataset
from nemo_platform import AsyncNeMoPlatform
from pytest_mock import MockerFixture


class _FakeFilesetFileSystem:
    def __init__(self, sdk: object) -> None:
        self._sdk = sdk

    async def _get_file(self, remote_path: str, local_path: str) -> None:
        raise AssertionError(f"unexpected download to {local_path} from {remote_path}")

    async def _get(self, remote_path: str, local_path: str, *, recursive: bool) -> None:
        raise AssertionError(f"unexpected recursive={recursive} download to {local_path} from {remote_path}")


@pytest.mark.asyncio
async def test_download_dataset_rejects_fragment_path_escape(mocker: MockerFixture, tmp_path: Path) -> None:
    """Fileset fragments should not write outside the requested destination."""
    mocker.patch("nemo_evaluator.filesets.FilesetFileSystem", _FakeFilesetFileSystem)

    with pytest.raises(ValueError, match="Fileset path escapes destination"):
        await download_dataset(
            cast(AsyncNeMoPlatform, object()),
            FilesetRef(root="default/helpsteer2#../../outside.jsonl"),
            str(tmp_path),
        )


@pytest.mark.asyncio
async def test_download_dataset_rejects_absolute_root_path(mocker: MockerFixture, tmp_path: Path) -> None:
    """Fileset roots should not be able to become absolute local paths."""
    mocker.patch("nemo_evaluator.filesets.FilesetFileSystem", _FakeFilesetFileSystem)

    with pytest.raises(ValueError, match="Fileset path escapes destination"):
        await download_dataset(
            cast(AsyncNeMoPlatform, object()),
            FilesetRef(root="/tmp/outside"),
            str(tmp_path),
        )
