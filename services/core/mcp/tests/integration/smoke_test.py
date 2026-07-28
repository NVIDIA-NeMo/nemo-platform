# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Integration smoke test for NeMo MCP server.

Creates and tests an MCP server instance that is connected to a running NeMo Platform instance.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Generator

import pytest
from nmp.common.sdk_factory import get_platform_sdk
from nmp.core.mcp.server import create_server

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from nemo_platform import NeMoPlatform


@pytest.fixture(scope="module")
def nmp_base_url() -> str:
    """Get NeMo Platform base URL from environment or use default."""
    return os.environ.get("NMP_BASE_URL", "http://localhost:8080")


@pytest.fixture(scope="module")
def nemo_sdk(nmp_base_url: str) -> Generator[NeMoPlatform, None, None]:
    """Create NeMo SDK client for direct API validation."""
    client = get_platform_sdk(base_url=nmp_base_url)
    yield client


@pytest.fixture(scope="module")
def mcp_server(nmp_base_url: str) -> Generator[FastMCP, None, None]:
    """Create MCP server instance."""
    server = create_server(nmp_base_url)
    yield server


class TestMCPServerSmoke:
    """Smoke tests for MCP server basic functionality."""

    def test_nmp_connection(self, nemo_sdk: NeMoPlatform) -> None:
        """Verify we can connect to NeMo Platform instance."""
        # This will raise if NeMo Platform is not accessible
        response = nemo_sdk.workspaces.list()
        assert response is not None
        assert hasattr(response, "data")

    def test_mcp_server_created(self, mcp_server: FastMCP) -> None:
        """Verify MCP server instance is created."""
        assert mcp_server is not None

    @pytest.mark.asyncio
    async def test_list_workspaces_tool_registered(self, mcp_server: FastMCP) -> None:
        """Verify list_workspaces tool is registered."""
        tools = await mcp_server.list_tools()
        tool_names = [t.name for t in tools]
        assert "list_workspaces" in tool_names

    @pytest.mark.asyncio
    async def test_list_workspaces_matches_sdk(self, mcp_server: FastMCP, nemo_sdk: NeMoPlatform) -> None:
        """
        Verify MCP tool returns consistent data with SDK.

        This ensures the MCP server is properly connected to NeMo Platform
        and returning real data.
        """
        import json

        # Get workspaces via SDK
        sdk_response = nemo_sdk.workspaces.list()
        sdk_workspace_ids = {ws.id for ws in sdk_response.data}

        # Get workspaces via MCP tool
        tool_result = await mcp_server.call_tool("list_workspaces", {})

        mcp_result = json.loads(tool_result.content[0].text)
        assert isinstance(mcp_result, dict)  # Type narrowing for ty

        # Verify MCP returns same workspace IDs
        mcp_workspace_ids = {ws["id"] for ws in mcp_result["workspaces"]}

        assert sdk_workspace_ids == mcp_workspace_ids, (
            f"MCP workspaces {mcp_workspace_ids} should match SDK workspaces {sdk_workspace_ids}"
        )

        # Verify counts match
        assert mcp_result["total"] == len(sdk_response.data), (
            f"MCP total {mcp_result['total']} should match SDK count {len(sdk_response.data)}"
        )

    @pytest.mark.asyncio
    async def test_list_workspaces_error_handling(self, nmp_base_url: str) -> None:
        """
        Verify tool handles connection errors gracefully.

        Creates a server with invalid URL to test error handling.
        """
        import json

        # Create server with invalid URL
        bad_server = create_server("http://invalid-host:9999")

        # Execute tool - should return error, not raise
        tool_result = await bad_server.call_tool("list_workspaces", {})

        result = json.loads(tool_result.content[0].text)

        # Verify error response structure
        assert isinstance(result, dict)
        assert result["success"] is False, "Should indicate failure"
        assert "error" in result, "Should contain error message"
        assert "error_type" in result, "Should contain error type"
