# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for model weight downloading via Files API."""

import asyncio
from pathlib import Path

import httpx
import pytest
import respx
from nemo_safe_synthesizer_plugin.tasks.safe_synthesizer.model_init import (
    ModelFileset,
    download_model_fileset,
    is_model_cached,
)

TEST_WORKSPACE = "model-init-test"


@pytest.fixture
def hf_cache_dir(tmp_path: Path) -> Path:
    """Temporary HuggingFace cache directory for tests."""
    cache_dir = tmp_path / "hf_cache"
    cache_dir.mkdir()
    return cache_dir


def _create_respx_route_for_files_api(workspace: str, fileset_name: str, files: dict[str, bytes], base_url: str):
    list_url = f"{base_url}/v2/workspaces/{workspace}/filesets/{fileset_name}/files"
    respx.get(list_url).respond(
        status_code=200,
        json={"data": [{"path": path, "size": len(content)} for path, content in files.items()]},
    )

    for path, content in files.items():
        download_url = f"{base_url}/v2/workspaces/{workspace}/filesets/{fileset_name}/-/{path}"
        respx.get(download_url).respond(status_code=200, content=content)


@respx.mock
@pytest.mark.integration
def test_download_single_file_model(hf_cache_dir: Path):
    fileset_name = "test-single-file-model"
    base_url = "http://files-api"
    config_content = b'{"model_type": "test", "hidden_size": 256}'
    _create_respx_route_for_files_api(TEST_WORKSPACE, fileset_name, {"config.json": config_content}, base_url)
    model_fileset = ModelFileset(
        workspace=TEST_WORKSPACE,
        name=fileset_name,
        hf_model_id="test-org/single-file-model",
    )

    async def run_download():
        async with httpx.AsyncClient(base_url=base_url) as client:
            return await download_model_fileset(client, base_url, model_fileset, hf_home=str(hf_cache_dir))

    assert asyncio.run(run_download()) is True
    model_dir = hf_cache_dir / "hub" / "models--test-org--single-file-model"
    snapshot_hash = (model_dir / "refs" / "main").read_text()
    config_path = model_dir / "snapshots" / snapshot_hash / "config.json"
    assert config_path.read_bytes() == config_content


@respx.mock
@pytest.mark.integration
def test_is_model_cached_after_download(hf_cache_dir: Path):
    fileset_name = "test-cache-check-model"
    model_id = "test-org/cache-check-model"
    base_url = "http://files-api"
    assert is_model_cached(model_id, str(hf_cache_dir)) is False
    _create_respx_route_for_files_api(TEST_WORKSPACE, fileset_name, {"config.json": b"{}"}, base_url)
    model_fileset = ModelFileset(workspace=TEST_WORKSPACE, name=fileset_name, hf_model_id=model_id)

    async def run_download():
        async with httpx.AsyncClient(base_url=base_url) as client:
            return await download_model_fileset(client, base_url, model_fileset, hf_home=str(hf_cache_dir))

    assert asyncio.run(run_download()) is True
    assert is_model_cached(model_id, str(hf_cache_dir)) is True
