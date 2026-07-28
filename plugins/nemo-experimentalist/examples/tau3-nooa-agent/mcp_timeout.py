# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Streamable-HTTP MCP client that tolerates slow tools.

nooa 0.0.6 builds its transport with ``httpx.AsyncClient(headers=...)`` and no
``timeout``, so httpx's 5 second default governs the MCP read stream. Passing a
pre-built client also means the MCP SDK's own, more generous defaults never apply.

The tau3-runtime sidecar drives a user-simulator LLM inside ``start_conversation``
and ``send_message_to_user``, which take longer than 5 seconds. The server finishes
the work and the run state advances, but the reply arrives on a stream httpx has
already abandoned, and nooa never surfaces a timeout, so the agent waits forever.

Drop this module and use ``MCPManager.create_from_server`` directly once nooa lets
callers set the transport timeout.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from nooa.mcp import MCPManager, MCPStreamableHTTPClient, MCPTool


class SlowToolStreamableHTTPClient(MCPStreamableHTTPClient):
    """``MCPStreamableHTTPClient`` whose read timeout matches ``tool_call_timeout``."""

    @asynccontextmanager
    async def connect_to_server(self) -> AsyncGenerator[ClientSession, None]:
        timeout = httpx.Timeout(self.tool_call_timeout.total_seconds())
        http_client = httpx.AsyncClient(headers=self.headers or None, timeout=timeout)
        async with (
            http_client,
            streamable_http_client(url=self.url, http_client=http_client) as (read, write, _),
            ClientSession(read, write, read_timeout_seconds=self.tool_call_timeout) as session,
        ):
            await session.initialize()
            yield session


def create_tool(server_name: str, url: str, tool_call_timeout: timedelta) -> MCPTool:
    """Build a tool for *server_name* that keeps nooa's generated per-tool methods.

    ``create_from_server`` discovers the server's tools and generates a class with a
    method per tool, which is the interface the agent's own code calls. Discovery is
    quick enough for the default transport; only the class is reused, rebound to a
    client that can wait out the slow calls.
    """
    discovered = MCPManager.create_from_server(server_name, url=url, transport="streamable-http")
    client = SlowToolStreamableHTTPClient(url=url, tool_call_timeout=tool_call_timeout)
    return type(discovered)(client, server_name)
