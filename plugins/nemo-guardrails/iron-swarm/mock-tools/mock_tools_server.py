# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mock Quill tools as a local stdio MCP server (for the Fabric demo).

Fabric's deepagents adapter cannot take in-process Python tools (executable
objects can't cross the config->JSON boundary), so tools come from an MCP server.
This is a tiny stdio server exposing Quill's four tools with CANNED results, so
``fabric_demo.py`` is a real end-to-end run: the model makes a real tool call, the
guardrail gates it, and the mock just returns stub data.

Tool names must match the ``guardrail__<tool>__*`` tasks in
guardrails_config/prompts.yml (and your real tool names when you swap this out).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("quill-tools")


@mcp.tool()
def list_saved_queries(query: str = "") -> dict:
    """List saved analytics queries matching an optional filter."""
    return {"saved_queries": ["daily_active_users", "q3_revenue"]}


@mcp.tool()
def run_sql(sql: str) -> dict:
    """Run a read-only SQL query against the data warehouse."""
    return {"rows": [[42]], "columns": ["count"]}


@mcp.tool()
def describe_schema(table: str) -> dict:
    """Describe the columns of a single table in the data warehouse."""
    return {"table": table, "columns": [{"name": "id", "type": "bigint"}, {"name": "created_at", "type": "timestamp"}]}


@mcp.tool()
def export_query_result(query_id: str, destination: str) -> dict:
    """Export a saved query's result to a destination (e.g. an email address)."""
    return {"exported": query_id, "destination": destination, "status": "ok"}


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
