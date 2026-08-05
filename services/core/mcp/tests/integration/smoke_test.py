# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Integration smoke test for NeMo MCP server.

Creates and tests an MCP server instance that is connected to a running NeMo Platform instance.
"""

from __future__ import annotations

import os
from typing import Any, Generator

import pytest
from fastmcp import FastMCP
from mcp.types import TextContent
from nemo_platform import NeMoPlatform
from nmp.common.sdk_factory import get_platform_sdk
from nmp.core.mcp.server import create_server


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


def _text_content(tool_result: Any) -> str:
    first_content = tool_result.content[0]
    assert isinstance(first_content, TextContent)
    return first_content.text


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

        mcp_result = json.loads(_text_content(tool_result))
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
    async def test_list_workspaces_error_handling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify tool handles connection errors gracefully.

        Mounts a controlled failing tool to test error handling.
        """
        import json

        import nmp.core.mcp.server as mcp_server_module
        from nmp.common.mcp import format_error_response

        def create_failing_entities_mcp(_base_url: str | None = None) -> FastMCP:
            server = FastMCP("Failing Entities Service")

            @server.tool(description="List workspaces in the NeMo platform")
            async def list_workspaces() -> dict[str, object]:
                try:
                    raise RuntimeError("platform unavailable")
                except Exception as e:
                    return format_error_response(e)

            return server

        monkeypatch.setattr(mcp_server_module, "create_entities_mcp", create_failing_entities_mcp)
        bad_server = mcp_server_module.create_server("http://unused.example.com")

        # Execute tool - should return error, not raise
        tool_result = await bad_server.call_tool("list_workspaces", {})

        result = json.loads(_text_content(tool_result))

        # Verify error response structure
        assert isinstance(result, dict)
        assert result["success"] is False, "Should indicate failure"
        assert "error_type" not in result
        assert isinstance(result["error"], dict), "Should contain structured error details"
        assert result["error"]["code"], "Should contain stable error code"
        assert result["error"]["message"], "Should contain error message"
        assert result["error"]["hint"], "Should contain remediation hint"
