# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Studio local coding-agent bridge."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from nmp.studio import coding_agents
from nmp.studio.service import StudioService


@pytest.fixture(autouse=True)
def reset_coding_agent_state():
    """Reset module-level bridge state between tests."""
    coding_agents._initialized_sessions.clear()
    coding_agents._session_streams.clear()
    coding_agents._pending_permissions.clear()
    yield
    coding_agents._initialized_sessions.clear()
    coding_agents._session_streams.clear()
    coding_agents._pending_permissions.clear()


@pytest.fixture
def service_client() -> TestClient:
    service = StudioService()
    return TestClient(service.app)


def test_create_session_returns_uuid(service_client: TestClient):
    response = service_client.post("/v2/coding-agents/sessions")

    assert response.status_code == 200
    uuid.UUID(response.json()["session_id"])


def test_build_claude_argv_uses_new_session_then_resume_flag():
    session_id = str(uuid.uuid4())

    argv = coding_agents._build_claude_argv(session_id, "hello", "http://test/mcp")
    assert argv[:3] == ["claude", "-p", "hello"]
    assert "--output-format" in argv
    assert "stream-json" in argv
    assert "--permission-prompt-tool" in argv
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__approval_prompt" in argv
    assert "--session-id" in argv
    assert session_id in argv

    coding_agents._initialized_sessions.add(session_id)
    resumed_argv = coding_agents._build_claude_argv(session_id, "again", "http://test/mcp")
    assert "-r" in resumed_argv
    assert "--session-id" not in resumed_argv


def test_list_and_get_history_sessions(
    service_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    workdir = tmp_path / "repo"
    projects_dir = tmp_path / "claude-projects"
    project_dir = projects_dir / str(workdir).replace("/", "-")
    project_dir.mkdir(parents=True)
    session_id = str(uuid.uuid4())
    history = project_dir / f"{session_id}.jsonl"
    history.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": {"content": "first prompt"}}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "msg_1",
                            "content": [
                                {"type": "thinking", "thinking": "checking"},
                                {"type": "text", "text": "done"},
                                {
                                    "type": "tool_use",
                                    "id": "toolu_1",
                                    "name": "Bash",
                                    "input": {"command": "pwd"},
                                },
                            ],
                            "usage": {
                                "input_tokens": 10,
                                "cache_creation_input_tokens": 2,
                                "cache_read_input_tokens": 3,
                                "output_tokens": 4,
                            },
                        },
                        "requestId": "req_1",
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "toolu_1",
                                    "content": "done",
                                }
                            ]
                        },
                        "toolUseResult": {"totalTokens": 11},
                    }
                ),
                json.dumps({"type": "user", "isSidechain": True, "message": {"content": "ignored"}}),
                "not-json",
            ]
        )
    )

    monkeypatch.setattr(coding_agents, "SERVER_CWD", workdir)
    monkeypatch.setattr(coding_agents, "CLAUDE_PROJECTS_DIR", projects_dir)

    list_response = service_client.get("/v2/coding-agents/history/sessions")

    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            "session_id": session_id,
            "mtime": history.stat().st_mtime,
            "first_prompt": "first prompt",
            "message_count": 1,
            "token_count": 30,
            "tool_call_count": 1,
            "tool_calls": ["Bash"],
        }
    ]

    history_response = service_client.get(f"/v2/coding-agents/history/sessions/{session_id}")

    assert history_response.status_code == 200
    assert history_response.json() == {
        "session_id": session_id,
        "items": [
            {"kind": "user", "text": "first prompt"},
            {
                "kind": "assistant",
                "parts": [
                    {"type": "thinking", "thinking": "checking"},
                    {"type": "text", "text": "done"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "pwd"}},
                ],
            },
        ],
    }
    assert session_id in coding_agents._initialized_sessions


def test_invalid_session_id_returns_400(service_client: TestClient):
    response = service_client.get("/v2/coding-agents/history/sessions/not-a-uuid")

    assert response.status_code == 400
    assert response.json()["detail"] == "session_id must be a UUID"


async def test_stream_claude_hides_startup_oserror(monkeypatch: pytest.MonkeyPatch):
    session_id = str(uuid.uuid4())

    async def fail_start(*args: Any, **kwargs: Any):
        raise OSError("secret local path")

    monkeypatch.setattr(coding_agents.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(coding_agents.asyncio, "create_subprocess_exec", fail_start)

    chunks = [chunk async for chunk in coding_agents._stream_claude(session_id, "hello", "http://test/mcp")]

    assert chunks == ['event: error\ndata: {"exit_code": null, "stderr": "Failed to start Claude Code process"}\n\n']
    assert "secret local path" not in chunks[0]
    assert session_id not in coding_agents._session_streams


def test_mcp_initialize_and_tools_list(service_client: TestClient):
    session_id = str(uuid.uuid4())

    initialize_response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    tools_response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert initialize_response.status_code == 200
    assert initialize_response.json()["result"]["serverInfo"]["name"] == "nemo-studio-permissions"
    assert tools_response.status_code == 200
    assert tools_response.json()["result"]["tools"][0]["name"] == "approval_prompt"


def test_mcp_rejects_malformed_json(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        content="{",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid JSON body"


def test_mcp_rejects_non_object_json(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(f"/v2/coding-agents/mcp/{session_id}", json=[])

    assert response.status_code == 400
    assert response.json()["detail"] == "JSON body must be an object"


def test_mcp_rejects_non_object_params(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "JSON-RPC params must be an object"


def test_mcp_tools_call_denies_without_active_stream(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "approval_prompt",
                "arguments": {"tool_name": "Bash", "input": {"command": "pwd"}},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "behavior": "deny",
        "message": "no active Studio coding-agent session",
    }


async def test_resolve_permission_rejects_cross_session_request():
    owner_session_id = str(uuid.uuid4())
    other_session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    coding_agents._pending_permissions[request_id] = (owner_session_id, future)

    with pytest.raises(HTTPException) as exc_info:
        await coding_agents.resolve_permission(
            other_session_id,
            request_id,
            coding_agents.PermissionDecision(approved=True),
        )

    assert exc_info.value.status_code == 404
    assert not future.done()


async def test_resolve_permission_sets_result_for_owning_session():
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    coding_agents._pending_permissions[request_id] = (session_id, future)

    response = await coding_agents.resolve_permission(
        session_id,
        request_id,
        coding_agents.PermissionDecision(approved=True),
    )

    assert response == {"ok": True}
    assert future.result() == {"approved": True, "reason": None, "updated_input": None}


def test_platform_route_stream_uses_public_mcp_callback(monkeypatch: pytest.MonkeyPatch):
    service = StudioService()
    app = FastAPI()
    app.include_router(service.app.router, prefix="/apis/studio")
    service.configure_app(app)
    client = TestClient(app)
    session_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    async def fake_stream(session_id: str, message: str, mcp_url: str):
        captured.update({"session_id": session_id, "message": message, "mcp_url": mcp_url})
        yield coding_agents._sse(json.dumps({"type": "system", "subtype": "init"}))
        yield coding_agents._sse("", event="done")

    monkeypatch.setattr(coding_agents, "_stream_claude", fake_stream)

    response = client.post(
        f"/apis/studio/v2/coding-agents/sessions/{session_id}/messages",
        json={"message": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in response.text
    assert captured == {
        "session_id": session_id,
        "message": "hello",
        "mcp_url": f"http://testserver/studio/api/coding-agents/mcp/{session_id}",
    }


def test_public_mcp_route_is_mounted_before_static_fallback():
    service = StudioService()
    app = FastAPI()
    service.configure_app(app)
    client = TestClient(app)
    session_id = str(uuid.uuid4())

    response = client.post(
        f"/studio/api/coding-agents/mcp/{session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["tools"][0]["name"] == "approval_prompt"


def test_coding_agent_routes_are_available_by_default():
    client = TestClient(StudioService().app)

    response = client.post("/v2/coding-agents/sessions")

    assert response.status_code == 200
    uuid.UUID(response.json()["session_id"])
