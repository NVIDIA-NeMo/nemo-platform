# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the MCP server status probe.

The stdio cases spawn real subprocesses — a working MCP server, a command that
exits immediately, and a command that is not on PATH — because the failure this
probe exists to catch is exactly a subprocess that does not come up.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.mcp_status import declared_mcp_servers, probe_mcp_servers

# A minimal stdio MCP server that advertises one tool.
_WORKING_SERVER = textwrap.dedent(
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("probe-test")

    @server.tool()
    def extract_iocs(text: str) -> str:
        return text

    server.run()
    """
)

_CRASHING_SERVER = "import sys; sys.stderr.write('ModuleNotFoundError: no such package\\n'); sys.exit(1)"


def _config(servers: dict[str, dict[str, Any]]) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "config_format": "nemo-agents-spec-v1",
            "name": "probe-agent",
            "default_harness": "hermes",
            "harnesses": {"hermes": {"kind": "hermes"}},
            "mcp": {"servers": servers},
        }
    )


class TestDeclaredMcpServers:
    def test_lists_every_declared_server_as_not_started(self) -> None:
        config = _config(
            {
                "iocs": {"transport": "stdio", "url": "email-security-triage-iocs"},
                "docs": {"transport": "streamable_http", "url": "https://example.invalid/mcp"},
            }
        )

        statuses = declared_mcp_servers(config)

        assert [s.name for s in statuses] == ["docs", "iocs"]
        assert {s.state for s in statuses} == {"not_started"}
        assert statuses[1].target == "email-security-triage-iocs"

    def test_no_mcp_section_declares_nothing(self) -> None:
        config = AgentConfig.model_validate(
            {
                "config_format": "nemo-agents-spec-v1",
                "name": "probe-agent",
                "default_harness": "hermes",
                "harnesses": {"hermes": {"kind": "hermes"}},
            }
        )

        assert declared_mcp_servers(config) == []


class TestProbeStdioServers:
    async def test_command_not_on_path_is_unresolved(self) -> None:
        config = _config({"iocs": {"transport": "stdio", "url": "nemo-mcp-server-that-is-not-installed"}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unresolved"
        assert status.command_resolved is False
        assert status.detail == "Command not found."
        # The PATH the probe searched is host layout, not status.
        assert os.environ["PATH"] not in status.detail

    async def test_resolved_command_that_dies_is_spawn_failed_with_generic_error(self) -> None:
        config = _config(
            {
                "iocs": {
                    "transport": "stdio",
                    "url": sys.executable,
                    "args": ["-c", _CRASHING_SERVER],
                }
            }
        )

        [status] = await probe_mcp_servers(config, timeout=15)

        assert status.state == "spawn_failed"
        assert status.command_resolved is True
        assert status.error == "Server exited before initializing."
        assert "ModuleNotFoundError" not in status.error

    async def test_working_server_is_running_and_lists_its_tools(self, tmp_path: Path) -> None:
        script = tmp_path / "server.py"
        script.write_text(_WORKING_SERVER, encoding="utf-8")
        config = _config(
            {
                "iocs": {
                    "transport": "stdio",
                    "url": sys.executable,
                    "args": [str(script)],
                }
            }
        )

        [status] = await probe_mcp_servers(config, timeout=30)

        assert status.state == "running", status.error
        assert status.command_resolved is True
        assert status.tools == ["extract_iocs"]

    async def test_empty_command_is_unresolved(self) -> None:
        config = _config({"iocs": {"transport": "stdio", "url": "   "}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unresolved"


class TestStderrNotExposed:
    """A crashed server's stderr — which can hold whatever its declared env held — never reaches the API."""

    async def test_stderr_secret_env_value_is_not_in_the_response(self) -> None:
        secret = "sk-super-secret-token-value"  # noqa: S105 — test fixture, not a real credential.
        server = "import os, sys; sys.stderr.write(os.environ['API_KEY']); sys.exit(1)"
        config = _config(
            {
                "iocs": {
                    "transport": "stdio",
                    "url": sys.executable,
                    "args": ["-c", server],
                    "env": {"API_KEY": secret},
                }
            }
        )

        [status] = await probe_mcp_servers(config, timeout=15)

        assert status.state == "spawn_failed"
        assert secret not in status.error
        assert status.error == "Server exited before initializing."


class TestProbeRemoteServers:
    async def test_unreachable_remote_server_is_reported(self) -> None:
        config = _config({"docs": {"transport": "streamable_http", "url": "http://127.0.0.1:1/mcp"}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unreachable"
        assert status.error

    async def test_reachable_remote_server_is_running(self, httpx_mock_url: str) -> None:
        config = _config({"docs": {"transport": "streamable_http", "url": httpx_mock_url}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "running"
        assert status.detail == "Responded with HTTP 200."

    async def test_client_error_response_is_not_running(self, httpx_status_url) -> None:
        url = httpx_status_url(404)
        config = _config({"docs": {"transport": "streamable_http", "url": url}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unreachable"
        assert status.detail == "Responded with HTTP 404."

    async def test_server_error_response_is_not_running(self, httpx_status_url) -> None:
        url = httpx_status_url(500)
        config = _config({"docs": {"transport": "streamable_http", "url": url}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unreachable"
        assert status.detail == "Responded with HTTP 500."

    async def test_redirect_response_is_not_running(self, httpx_status_url) -> None:
        url = httpx_status_url(302)
        config = _config({"docs": {"transport": "streamable_http", "url": url}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unreachable"
        assert status.detail == "Responded with HTTP 302."


class TestProbeUnknownTransport:
    async def test_unknown_transport_is_not_checked(self) -> None:
        config = _config({"weird": {"transport": "carrier-pigeon", "url": "somewhere"}})

        [status] = await probe_mcp_servers(config, timeout=5)

        assert status.state == "unknown"
        assert status.detail == "Unsupported transport 'carrier-pigeon'."


@pytest.fixture
def httpx_mock_url() -> Any:
    """A URL that answers 200, served by respx rather than a real socket."""
    import respx

    url = "https://mcp.example.invalid/mcp"
    with respx.mock:
        respx.get(url).respond(200)
        yield url


@pytest.fixture
def httpx_status_url() -> Any:
    """A factory for a URL that answers with a given status code, via respx."""
    import respx

    url = "https://mcp.example.invalid/mcp"
    with respx.mock:

        def _make(status_code: int) -> str:
            respx.get(url).respond(status_code)
            return url

        yield _make
