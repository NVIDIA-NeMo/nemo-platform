# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Fabric calculator example."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from nemo_agents_plugin.agent_config import apply_agent_profiles, load_agent_config, load_agent_profile
from nemo_agents_plugin.fabric.translator import translate_agent_config
from nemo_fabric import Fabric  # ty: ignore[unresolved-import]

EXAMPLE_DIR = Path(__file__).parents[2] / "examples/fabric-calculator-agent"


def test_base_example_has_no_mcp_servers() -> None:
    config = load_agent_config(EXAMPLE_DIR / "agent.yaml")
    fabric_config = translate_agent_config(config)

    assert config.name == "fabric-calculator-agent"
    assert fabric_config.harness.adapter_id == "nvidia.fabric.codex"
    assert fabric_config.mcp is None
    assert fabric_config.relay is not None

    plan = Fabric().plan(fabric_config, base_dir=EXAMPLE_DIR)
    assert plan.adapter.adapter_id == "nvidia.fabric.codex"
    assert "mcp_servers" not in plan.capability_plan


def test_with_mcp_profile_adds_harness_native_stdio_server() -> None:
    config = load_agent_config(EXAMPLE_DIR / "agent.yaml")
    profile = load_agent_profile(EXAMPLE_DIR / "profiles/with-mcp.yaml")

    fabric_config = translate_agent_config(apply_agent_profiles(config, [profile]))

    assert fabric_config.mcp is not None
    calculator = fabric_config.mcp.servers["calculator"]
    assert calculator.transport == "stdio"
    assert calculator.url == "fabric-calculator-mcp"
    assert calculator.exposure == "harness_native"

    plan = Fabric().plan(fabric_config, base_dir=EXAMPLE_DIR)
    assert list(plan.capability_plan["native"]["mcp_servers"]) == ["calculator"]


@pytest.mark.asyncio
async def test_calculator_mcp_server_over_stdio() -> None:
    server = StdioServerParameters(command="fabric-calculator-mcp")

    async with stdio_client(server) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("multiply", {"numbers": [12, 8]})

    assert {tool.name for tool in tools.tools} == {"add", "subtract", "multiply", "divide", "compare"}
    assert result.isError is False
    assert result.structuredContent == {"result": 96.0}
