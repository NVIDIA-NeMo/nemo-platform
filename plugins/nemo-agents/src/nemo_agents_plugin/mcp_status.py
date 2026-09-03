# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime status of the MCP servers an agent declares.

An agent that declares a stdio MCP server degrades silently when the server
never spawns: the harness simply gets fewer tools. The models here describe,
per declared server, whether the runtime can actually reach it, and
:func:`probe_mcp_servers` produces that answer *from inside the runtime
process* so the ``PATH`` a stdio command is resolved against is the one the
subprocess would really inherit.

Nothing here reports host filesystem layout. Whether a stdio command resolved
is a boolean, never a path; messages are one short sentence and never quote the
``PATH`` that was searched; and any absolute path that still reaches a message
or a captured stderr snippet is reduced to its final component on the way out.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from typing import IO, Literal

from nemo_agents_plugin.agent_config import AgentConfig, McpServerConfig
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Transport spellings the Fabric adapters normalize to a stdio subprocess.
_STDIO_TRANSPORTS = frozenset({"stdio", "command", "process"})
# Transport spellings that address a server over the network. An empty
# transport means streamable HTTP, matching adapter normalization.
_REMOTE_TRANSPORTS = frozenset({"", "http", "streamable_http", "streamablehttp", "sse", "websocket"})

DEFAULT_PROBE_TIMEOUT_SECONDS = 10.0

# Bytes of captured stderr kept for a failed launch. Enough for a traceback's
# last frames without turning the status response into a log dump.
_STDERR_SNIPPET_BYTES = 2000

McpServerState = Literal[
    "running",
    "unresolved",
    "spawn_failed",
    "unreachable",
    "not_started",
    "unknown",
]


class McpServerStatus(BaseModel):
    """Runtime state of one MCP server an agent declares."""

    name: str = Field(description="Server name as declared under mcp.servers in the agent config.")
    transport: str = Field(description="Transport as declared (e.g. 'stdio', 'streamable_http').")
    target: str = Field(description="Command to spawn for stdio servers, or the endpoint URL for remote ones.")
    args: list[str] = Field(default_factory=list, description="Arguments passed to a stdio command.")
    exposure: str = Field(default="", description="'harness_native' or 'fabric_managed'.")
    state: McpServerState = Field(
        description=(
            "running: reachable and initialized. unresolved: stdio command not found on the runtime PATH. "
            "spawn_failed: command resolved but the server died or never initialized. "
            "unreachable: remote server did not answer. not_started: nothing is running to check against. "
            "unknown: transport not understood, so no check was made."
        )
    )
    command_resolved: bool = Field(
        default=False,
        description=(
            "Whether a stdio command was found on the runtime PATH. Always false for remote "
            "transports, which have no command to resolve. The path it resolved to is "
            "deliberately not reported."
        ),
    )
    detail: str = Field(default="", description="Human-readable explanation of the state.")
    error: str = Field(default="", description="Error message or stderr snippet when the server failed to start.")
    tools: list[str] = Field(default_factory=list, description="Tool names the server advertised, when it started.")


class McpStatusResponse(BaseModel):
    """A runtime's answer to "are your MCP servers up?"."""

    runtime_instance_id: str = Field(default="", description="Id of the runtime process that ran the check.")
    checked_at: datetime = Field(description="When the check ran.")
    servers: list[McpServerStatus] = Field(default_factory=list, description="One entry per declared MCP server.")


def declared_mcp_servers(config: AgentConfig) -> list[McpServerStatus]:
    """Return every declared server as a ``not_started`` status, in name order."""
    servers = config.mcp.servers if config.mcp is not None else {}
    return [
        _base_status(
            name,
            server,
            state="not_started",
            detail="Agent is not deployed.",
        )
        for name, server in sorted(servers.items())
    ]


async def probe_mcp_servers(
    config: AgentConfig,
    *,
    timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> list[McpServerStatus]:
    """Check every declared MCP server against the current process environment."""
    servers = config.mcp.servers if config.mcp is not None else {}
    ordered = sorted(servers.items())
    results = await asyncio.gather(*(_probe_server(name, server, timeout) for name, server in ordered))
    return list(results)


async def _probe_server(name: str, server: McpServerConfig, timeout: float) -> McpServerStatus:
    transport = _normalize_transport(server.transport)
    if transport in _STDIO_TRANSPORTS:
        return await _probe_stdio_server(name, server, timeout)
    if transport in _REMOTE_TRANSPORTS:
        return await _probe_remote_server(name, server, timeout)
    return _base_status(
        name,
        server,
        state="unknown",
        detail=f"Unsupported transport '{server.transport}'.",
    )


async def _probe_stdio_server(name: str, server: McpServerConfig, timeout: float) -> McpServerStatus:
    command = os.path.expandvars(server.url).strip()
    env = {**_default_environment(), **server.env}
    if not command:
        return _base_status(
            name,
            server,
            state="unresolved",
            detail="No command configured.",
        )

    if shutil.which(command, path=env.get("PATH")) is None:
        return _base_status(
            name,
            server,
            state="unresolved",
            detail="Command not found.",
        )

    started, tools, error = await _start_stdio_server(command, server.args, env, timeout)
    if not started:
        return _base_status(
            name,
            server,
            state="spawn_failed",
            command_resolved=True,
            detail="Server did not start.",
            error=error,
        )
    return _base_status(
        name,
        server,
        state="running",
        command_resolved=True,
        detail=f"Started with {len(tools)} tool(s).",
        tools=tools,
    )


async def _start_stdio_server(
    command: str,
    args: list[str],
    env: dict[str, str],
    timeout: float,
) -> tuple[bool, list[str], str]:
    """Spawn the server, initialize a session, and list its tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=list(args), env=env)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errlog:
        try:
            async with asyncio.timeout(timeout):
                async with stdio_client(params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        return True, [tool.name for tool in listed.tools], ""
        except TimeoutError:
            return False, [], _with_stderr(f"Server did not initialize within {timeout:g}s.", errlog)
        except Exception as exc:  # noqa: BLE001 — any launch failure is reportable status, not a 500.
            logger.debug("MCP stdio probe of '%s' failed", command, exc_info=True)
            return False, [], _with_stderr(f"{type(exc).__name__}: {exc}", errlog)


async def _probe_remote_server(name: str, server: McpServerConfig, timeout: float) -> McpServerStatus:
    """Check that a remote server answers."""
    import httpx

    url = os.path.expandvars(server.url).strip()
    if not url:
        return _base_status(
            name,
            server,
            state="unreachable",
            detail="No URL configured.",
        )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=server.custom_headers or None)
    except Exception as exc:  # noqa: BLE001 — connection failures are reportable status.
        logger.debug("MCP remote probe of '%s' failed", url, exc_info=True)
        return _base_status(
            name,
            server,
            state="unreachable",
            detail="Server did not respond.",
            error=f"{type(exc).__name__}: {exc}",
        )
    return _base_status(
        name,
        server,
        state="running",
        detail=f"Responded with HTTP {response.status_code}.",
    )


def _base_status(
    name: str,
    server: McpServerConfig,
    *,
    state: McpServerState,
    command_resolved: bool = False,
    detail: str = "",
    error: str = "",
    tools: list[str] | None = None,
) -> McpServerStatus:
    return McpServerStatus(
        name=name,
        transport=server.transport,
        target=_redact_paths(server.url),
        args=list(server.args),
        exposure=server.exposure,
        state=state,
        command_resolved=command_resolved,
        detail=_redact_paths(detail),
        error=_redact_paths(error),
        tools=tools or [],
    )


# An absolute POSIX path, not preceded by a word character, ':' or '/' so that
# URL paths ("http://host/mcp") and relative fragments are left alone.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w.:/])/(?:[^\s'\"()\\,;]+/)+([^\s'\"()\\,;]*)")


def _redact_paths(text: str) -> str:
    """Reduce absolute host paths in *text* to their final component."""
    return _ABSOLUTE_PATH_RE.sub(lambda match: f".../{match.group(1)}" if match.group(1) else ".../", text)


def _normalize_transport(transport: str) -> str:
    return transport.strip().lower().replace("-", "_")


def _default_environment() -> dict[str, str]:
    """The env an MCP stdio subprocess inherits, per the mcp SDK's allowlist."""
    from mcp.client.stdio import get_default_environment

    return get_default_environment()


def _with_stderr(message: str, errlog: IO[str]) -> str:
    """Append the tail of the server's stderr to *message*, when it wrote any."""
    try:
        errlog.flush()
        errlog.seek(0)
        snippet = errlog.read()[-_STDERR_SNIPPET_BYTES:].strip()
    except (OSError, ValueError):
        return message
    return f"{message}\n{snippet}" if snippet else message


def config_from_dict(config: dict) -> AgentConfig | None:
    """Load an agent config dict, returning None when it is not a v1 agent spec."""
    try:
        return AgentConfig.model_validate(config)
    except Exception:  # noqa: BLE001 — a NAT-format or malformed config simply declares no MCP servers here.
        return None
