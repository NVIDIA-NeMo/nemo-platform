# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Fabric one-shot invocation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from nemo_agents_plugin.fabric.invocation import invoke_agent_config_once
from nemo_agents_plugin.fabric.runtime import FabricRuntimeResult


def _agent_config() -> dict[str, Any]:
    return {
        "config_format": "nemo-agents-spec-v1",
        "name": "fabric-agent",
        "default_harness": "hermes",
        "harnesses": {
            "hermes": {
                "kind": "hermes",
            },
        },
        "models": {
            "default": {
                "provider": "openai",
                "model": "openai/gpt-5.4",
            },
        },
    }


@pytest.mark.asyncio
async def test_invoke_agent_config_once_translates_and_runs_each_input(tmp_path: Path) -> None:
    captured: list[Any] = []

    async def _run_fabric_agent_once(request: Any) -> FabricRuntimeResult:
        captured.append(request)
        return FabricRuntimeResult(status="succeeded", response=f"response:{request.input}")

    with patch("nemo_agents_plugin.fabric.invocation.run_fabric_agent_once", _run_fabric_agent_once):
        results = await invoke_agent_config_once(_agent_config(), ["one", "two"], base_dir=tmp_path)

    assert [result.response for result in results] == ["response:one", "response:two"]
    assert [request.input for request in captured] == ["one", "two"]
    assert all(request.base_dir == tmp_path for request in captured)
    assert captured[0].fabric_config.metadata.name == "fabric-agent"


@pytest.mark.asyncio
async def test_invoke_agent_config_once_creates_local_workspace_dir(tmp_path: Path) -> None:
    config = _agent_config()
    config["environment"] = {"workspace": "./workspace"}

    async def _run_fabric_agent_once(request: Any) -> FabricRuntimeResult:
        assert (tmp_path / "workspace").is_dir()
        return FabricRuntimeResult(status="succeeded")

    with patch("nemo_agents_plugin.fabric.invocation.run_fabric_agent_once", _run_fabric_agent_once):
        await invoke_agent_config_once(config, ["one"], base_dir=tmp_path)
