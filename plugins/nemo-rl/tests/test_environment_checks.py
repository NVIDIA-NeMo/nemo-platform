# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Submit-time environment FileSet validation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nemo_rl_plugin.environment import check_environment_package

ADAPTER_MANIFEST = b"""
format: adapter-wheels-v1
adapter:
  agent: verifiers_agent
config_paths:
  - configs/verifiers_agent.yaml
metadata:
  name: ascii-tree
"""

ADAPTER_FILES = [
    "nemo-environment.yaml",
    "configs/verifiers_agent.yaml",
    "wheels/ascii_tree-1.0-py3-none-any.whl",
]


def _sdk(paths: list[str], manifest: bytes = ADAPTER_MANIFEST) -> Mock:
    """Stub the Files client down to the two calls the check makes."""
    listing = SimpleNamespace(data=[SimpleNamespace(path=p) for p in paths])
    client = Mock()
    client.list_files = AsyncMock(return_value=SimpleNamespace(data=lambda: listing))
    client.download_file = AsyncMock(return_value=SimpleNamespace(read=AsyncMock(return_value=manifest)))
    return client


@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch):
    def _patch(client: Mock) -> None:
        monkeypatch.setattr("nemo_rl_plugin.environment.client_from_platform", lambda sdk, cls: client)

    return _patch


@pytest.mark.asyncio
async def test_valid_adapter_wheels_package_passes(patch_client) -> None:
    patch_client(_sdk(ADAPTER_FILES))
    await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_missing_manifest_is_rejected(patch_client) -> None:
    patch_client(_sdk(["configs/verifiers_agent.yaml"]))
    with pytest.raises(ValueError, match="nemo-environment.yaml"):
        await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_config_path_not_in_package_is_rejected(patch_client) -> None:
    """The manifest naming a file nobody uploaded is the common packaging slip.

    Left to the job, Gym starts, finds no config, and starts no servers -- which surfaces
    as rollouts timing out rather than as a missing file.
    """
    patch_client(_sdk(["nemo-environment.yaml", "wheels/x-1.0-py3-none-any.whl"]))
    with pytest.raises(ValueError, match="config_paths reference files that are not in the package"):
        await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_wheels_format_without_wheels_is_rejected(patch_client) -> None:
    patch_client(_sdk(["nemo-environment.yaml", "configs/verifiers_agent.yaml"]))
    with pytest.raises(ValueError, match="wheels/"):
        await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_unlisted_adapter_agent_is_rejected(patch_client) -> None:
    """adapter.agent selects code baked into the training image, so it is closed-set."""
    manifest = ADAPTER_MANIFEST.replace(b"agent: verifiers_agent", b"agent: some_other_agent")
    patch_client(_sdk(ADAPTER_FILES, manifest=manifest))
    with pytest.raises(ValueError, match="not built into the training image"):
        await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_prompt_jsonl_in_environment_is_rejected(patch_client) -> None:
    """Rows belong to the dataset FileSet; one environment is meant to serve many datasets."""
    patch_client(_sdk([*ADAPTER_FILES, "training.jsonl"]))
    with pytest.raises(ValueError, match="Prompt JSONL must not live in the environment package"):
        await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_malformed_manifest_is_rejected(patch_client) -> None:
    patch_client(_sdk(ADAPTER_FILES, manifest=b"format: no-such-format\nmetadata:\n  name: x\n"))
    with pytest.raises(ValueError, match="not a valid package"):
        await check_environment_package(Mock(), "default/env", "default")


@pytest.mark.asyncio
async def test_native_v1_needs_no_wheels(patch_client) -> None:
    manifest = b"""
format: native-v1
config_paths:
  - resources_servers/ascii_tree/configs/ascii_tree.yaml
metadata:
  name: ascii-tree
"""
    patch_client(_sdk(["nemo-environment.yaml", "resources_servers/ascii_tree/configs/ascii_tree.yaml"], manifest))
    await check_environment_package(Mock(), "default/env", "default")
