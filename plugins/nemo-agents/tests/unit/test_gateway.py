# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the agent gateway proxy routes.

Covers:
- 5xx from the upstream agent → 502 Bad Gateway
- 2xx responses streamed through with correct status and content-type
- Empty-body responses (e.g. 204) handled without error
- Agent not found → 404
- Deployment not running → 503
- httpx connection error → 502
- Proxy by agent name resolves the active deployment endpoint
- Proxy by deployment name targets the deployment directly

Mocking strategy: patch ``httpx.AsyncClient`` so tests run with no real network.
The mock replicates the async-context-manager chain::

    async with httpx.AsyncClient(...) as client:
        async with client.stream(...) as response:
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_agents_plugin.api.v2 import gateway as gateway_module
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.entities import Agent, AgentDeployment, DeploymentStatus
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(name: str = "calc", workspace: str = "default") -> Agent:
    return Agent(name=name, workspace=workspace)


def _make_deployment(
    name: str = "calc-dep",
    agent: str = "calc",
    workspace: str = "default",
    status: DeploymentStatus = "running",
    endpoint: str = "http://localhost:9001",
) -> AgentDeployment:
    return AgentDeployment(name=name, workspace=workspace, agent=agent, status=status, endpoint=endpoint)


def _list_response(items: list) -> MagicMock:
    resp = MagicMock()
    resp.data = items
    return resp


def _make_httpx_mock(
    status_code: int,
    body: bytes = b"",
    content_type: str = "application/json",
) -> MagicMock:
    """Build the full async-context-manager chain for httpx.AsyncClient().stream()."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = httpx.Headers({"content-type": content_type})

    async def _aiter_bytes():
        if body:
            yield body

    async def _aread():
        return body

    mock_response.aiter_bytes = _aiter_bytes
    mock_response.aread = _aread

    # client.stream(...) → async context manager yielding mock_response
    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=stream_cm)

    # httpx.AsyncClient(...) → async context manager yielding mock_client
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    return client_cm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_entity_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def test_app(mock_entity_client: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(
        gateway_module.router,
        prefix="/apis/agents/v2/workspaces/{workspace}",
    )
    app.dependency_overrides[get_entity_client] = lambda: mock_entity_client
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Proxy by deployment name — core proxy behaviour
# ---------------------------------------------------------------------------


class TestProxyByDeploymentName:
    def test_2xx_passed_through(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        upstream_body = b'{"answer": 42}'
        httpx_mock = _make_httpx_mock(200, upstream_body, "application/json")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 200
        assert resp.content == upstream_body

    def test_5xx_from_agent_becomes_502(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Agent 5xx responses must be translated to 502 Bad Gateway."""
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        error_body = b"Internal server error in agent"
        httpx_mock = _make_httpx_mock(500, error_body)

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={"messages": []},
            )

        assert resp.status_code == 502
        assert "502" in resp.text or "Agent returned 500" in resp.text

    def test_503_from_agent_becomes_502(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Any 5xx (not just 500) is translated to 502."""
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        httpx_mock = _make_httpx_mock(503, b"Service Unavailable")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={},
            )

        assert resp.status_code == 502

    def test_4xx_from_agent_passed_through(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """4xx client errors from the agent are transparent pass-through."""
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        httpx_mock = _make_httpx_mock(422, b'{"detail": "invalid input"}')

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={},
            )

        assert resp.status_code == 422

    def test_empty_body_response_handled(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Empty body (e.g. 204 No Content) must not raise StopAsyncIteration."""
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        httpx_mock = _make_httpx_mock(204, b"")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={},
            )

        assert resp.status_code == 204

    def test_content_type_forwarded(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        httpx_mock = _make_httpx_mock(200, b"data: hello\n\n", "text/event-stream")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.get(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/stream",
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_connection_error_returns_502(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        # Simulate httpx.ConnectError during stream open
        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=client_cm):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={},
            )

        assert resp.status_code == 502
        assert "Could not connect" in resp.json()["detail"]

    def test_deployment_not_found_returns_404(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("not found"))

        resp = client.post(
            "/apis/agents/v2/workspaces/default/deployments/nonexistent/-/v1/chat/completions",
            json={},
        )

        assert resp.status_code == 404

    def test_deployment_not_running_returns_503(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        dep = _make_deployment(status="starting", endpoint="")
        mock_entity_client.get = AsyncMock(return_value=dep)

        resp = client.post(
            "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
            json={},
        )

        assert resp.status_code == 503
        assert "not running" in resp.json()["detail"].lower()

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "%2F%2Fevil.example.com/x",
            "http:%2F%2Fevil.example.com/x",
        ],
    )
    def test_cross_origin_trailing_uri_rejected(
        self, client: TestClient, mock_entity_client: AsyncMock, malicious_path: str
    ) -> None:
        """SSRF guard rejects trailing_uri values that resolve to a different host."""
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        resp = client.post(
            f"/apis/agents/v2/workspaces/default/deployments/calc-dep/-/{malicious_path}",
            json={},
        )

        assert resp.status_code == 400
        assert "invalid proxy target" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Proxy by agent name — endpoint resolution
# ---------------------------------------------------------------------------


class TestProxyByAgentName:
    def test_resolves_running_deployment(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(return_value=_make_agent("calc"))
        dep = _make_deployment(agent="calc", status="running", endpoint="http://localhost:9001")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        httpx_mock = _make_httpx_mock(200, b'{"ok": true}')

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/agents/calc/-/v1/chat/completions",
                json={"messages": []},
            )

        assert resp.status_code == 200

    def test_agent_not_found_returns_404(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("not found"))

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents/nonexistent/-/v1/chat/completions",
            json={},
        )

        assert resp.status_code == 404

    def test_no_running_deployment_returns_503(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get = AsyncMock(return_value=_make_agent("calc"))
        # Only a failed deployment — no running ones
        dep = _make_deployment(agent="calc", status="failed")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        resp = client.post(
            "/apis/agents/v2/workspaces/default/agents/calc/-/v1/chat/completions",
            json={},
        )

        assert resp.status_code == 503

    def test_5xx_from_agent_becomes_502_via_name(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """5xx translation works end-to-end through the agent-name proxy path too."""
        mock_entity_client.get = AsyncMock(return_value=_make_agent("calc"))
        dep = _make_deployment(agent="calc", status="running", endpoint="http://localhost:9001")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        httpx_mock = _make_httpx_mock(500, b"agent crashed")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/agents/calc/-/v1/chat/completions",
                json={},
            )

        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Model name patching — unknown-model → agent/deployment name
# ---------------------------------------------------------------------------


class TestModelNamePatching:
    def test_unknown_model_replaced_by_agent_name(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """JSON responses with "unknown-model" get patched to the agent name."""
        mock_entity_client.get = AsyncMock(return_value=_make_agent("my-agent"))
        dep = _make_deployment(agent="my-agent", status="running", endpoint="http://localhost:9001")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        body = json.dumps({"model": "unknown-model", "choices": [{"message": {"content": "hi"}}]}).encode()
        httpx_mock = _make_httpx_mock(200, body, "application/json")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/agents/my-agent/-/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "my-agent"
        assert data["choices"] == [{"message": {"content": "hi"}}]

    def test_malformed_json_passed_through(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Non-JSON response bodies are passed through unmodified."""
        mock_entity_client.get = AsyncMock(return_value=_make_agent("calc"))
        dep = _make_deployment(agent="calc", status="running", endpoint="http://localhost:9001")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        garbled = b"this is not json"
        httpx_mock = _make_httpx_mock(200, garbled, "application/json")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/agents/calc/-/v1/chat/completions",
                json={"messages": []},
            )

        assert resp.status_code == 200
        assert resp.content == garbled

    def test_real_model_not_replaced(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """JSON responses with a real model name are left untouched."""
        mock_entity_client.get = AsyncMock(return_value=_make_agent("calc"))
        dep = _make_deployment(agent="calc", status="running", endpoint="http://localhost:9001")
        mock_entity_client.list = AsyncMock(return_value=_list_response([dep]))

        body = json.dumps({"model": "gpt-4o", "choices": []}).encode()
        httpx_mock = _make_httpx_mock(200, body, "application/json")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/agents/calc/-/v1/chat/completions",
                json={"messages": []},
            )

        assert resp.status_code == 200
        assert resp.json()["model"] == "gpt-4o"

    def test_sse_stream_not_patched(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """SSE (event-stream) responses are passed through without model patching."""
        dep = _make_deployment(status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        sse_body = b'data: {"model":"unknown-model","choices":[]}\n\n'
        httpx_mock = _make_httpx_mock(200, sse_body, "text/event-stream")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-dep/-/v1/chat/completions",
                json={"messages": [], "stream": True},
            )

        assert resp.status_code == 200
        assert b"unknown-model" in resp.content

    def test_deployment_name_used_for_deployment_proxy(self, client: TestClient, mock_entity_client: AsyncMock) -> None:
        """Deployment-name proxy path patches model to the deployment name."""
        dep = _make_deployment(name="calc-v2", status="running", endpoint="http://localhost:9001")
        mock_entity_client.get = AsyncMock(return_value=dep)

        body = json.dumps({"model": "unknown-model", "choices": []}).encode()
        httpx_mock = _make_httpx_mock(200, body, "application/json")

        with patch("nemo_agents_plugin.api.v2.gateway.httpx.AsyncClient", return_value=httpx_mock):
            resp = client.post(
                "/apis/agents/v2/workspaces/default/deployments/calc-v2/-/v1/chat/completions",
                json={"messages": []},
            )

        assert resp.status_code == 200
        assert resp.json()["model"] == "calc-v2"
