# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import data_designer.config as dd
import httpx
import pytest
from data_designer_nemo.context import LocalDataDesignerContext
from data_designer_nemo.errors import NDDInvalidConfigError
from data_designer_nemo.seed import validate_seed
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.errors import NotFoundError


def _make_config(source: Any) -> dd.DataDesignerConfig:
    builder = dd.DataDesignerConfigBuilder()
    builder.with_seed_dataset(source)
    return builder.build()


@pytest.mark.asyncio
async def test_local_validate_seed_passes_existing_local_directory_without_sdk(tmp_path: Path) -> None:
    sdk = AsyncMock(spec=AsyncNeMoPlatform)

    validated_root = await validate_seed(
        _make_config(dd.DirectorySeedSource(path=str(tmp_path))), "default", sdk, is_local=True
    )

    assert validated_root is None
    sdk.files.filesets.retrieve.assert_not_called()
    sdk.files.list.assert_not_called()


@pytest.mark.asyncio
async def test_local_validate_seed_validates_fileset_for_non_local_path() -> None:
    sdk = AsyncMock(spec=AsyncNeMoPlatform)
    files = Mock()
    files.get_fileset = AsyncMock()
    files.list_files = AsyncMock(return_value=Mock(data=[Mock(path="corpus/a.md")]))

    with patch("data_designer_nemo.seed.client_from_platform", return_value=files):
        validated_root = await validate_seed(
            _make_config(dd.DirectorySeedSource(path="docs#corpus")), "default", sdk, is_local=True
        )

    assert validated_root == "default/docs#corpus"
    files.get_fileset.assert_awaited_once_with(name="docs", workspace="default")


@pytest.mark.asyncio
async def test_local_validate_seed_reports_missing_fileset() -> None:
    sdk = AsyncMock(spec=AsyncNeMoPlatform)
    files = Mock()
    files.get_fileset = AsyncMock(side_effect=NotFoundError(httpx.Response(404, text="missing")))

    with pytest.raises(NDDInvalidConfigError, match="Could not find fileset"):
        with patch("data_designer_nemo.seed.client_from_platform", return_value=files):
            await validate_seed(
                _make_config(dd.DirectorySeedSource(path="does-not-exist#corpus")), "default", sdk, is_local=True
            )


@pytest.mark.asyncio
async def test_local_validate_seed_skips_huggingface_secret_resolution() -> None:
    # Remote mode resolves the HF token against the Files/secret service; local mode must not,
    # since the token may be a plaintext value or an environment variable.
    sdk = AsyncMock(spec=AsyncNeMoPlatform)

    validated_root = await validate_seed(
        _make_config(dd.HuggingFaceSeedSource(path="org/dataset", token="hf_local_token")),
        "default",
        sdk,
        is_local=True,
    )

    assert validated_root is None


@pytest.mark.asyncio
async def test_local_context_validate_caches_fileset_root() -> None:
    sdk = AsyncMock(spec=AsyncNeMoPlatform)
    files = Mock()
    files.get_fileset = AsyncMock()
    files.list_files = AsyncMock(return_value=Mock(data=[Mock(path="corpus/a.md")]))
    ctx = LocalDataDesignerContext(sdk, "default")

    with patch("data_designer_nemo.seed.client_from_platform", return_value=files):
        errors = await ctx.validate(_make_config(dd.DirectorySeedSource(path="docs#corpus")))

    assert errors == []
    assert "default/docs#corpus" in ctx._validated_filesystem_roots
