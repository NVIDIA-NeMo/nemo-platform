# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Installed-discovery integration coverage for the NAT Fabric adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.invocation import invoke_agent_config_once


@pytest.mark.integration
@pytest.mark.asyncio
async def test_platform_invokes_installed_nat_adapter_without_local_descriptor(tmp_path: Path) -> None:
    (tmp_path / "workflow.yml").write_text(
        "workflow:\n  _type: current_timezone\n",
        encoding="utf-8",
    )
    agent_config = AgentConfig.model_validate(
        {
            "config_format": "nemo-agents-spec-v1",
            "name": "nat-installed-discovery",
            "default_harness": "nat",
            "harnesses": {
                "nat": {
                    "kind": "nat",
                    "settings": {
                        "config_file": "./workflow.yml",
                    },
                }
            },
            "environment": {
                "workspace": "./workspace",
                "artifacts": "./artifacts",
            },
            "telemetry": {
                "enabled": False,
            },
        }
    )

    results = await invoke_agent_config_once(agent_config, ["ignored"], base_dir=tmp_path)

    assert not (tmp_path / "adapters").exists()
    assert len(results) == 1
    result = results[0]
    assert result.status == "succeeded"
    assert isinstance(result.response, str)
    assert result.response.startswith("The time zone is ")
    assert result.output["mode"] == "nat_workflow"
    assert result.output["completed"] is True
    assert result.metadata["adapter_runner"] == "persistent_local_host"
