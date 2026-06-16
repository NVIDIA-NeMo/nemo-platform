# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Studio local coding-agent bridge."""

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from nmp.studio import coding_agent_skills, coding_agents, studio_links
from nmp.studio.config import StudioConfig
from nmp.studio.service import StudioService


@pytest.fixture(autouse=True)
def reset_coding_agent_state():
    """Reset module-level bridge state between tests."""
    coding_agents._initialized_sessions.clear()
    coding_agents._session_streams.clear()
    coding_agents._pending_permissions.clear()
    coding_agents._pending_agent_inputs.clear()
    yield
    coding_agents._initialized_sessions.clear()
    coding_agents._session_streams.clear()
    coding_agents._pending_permissions.clear()
    coding_agents._pending_agent_inputs.clear()


@pytest.fixture
def service_client() -> TestClient:
    service = StudioService()
    return TestClient(service.app)


def service_client_with_feature_flags(
    monkeypatch: pytest.MonkeyPatch, feature_flags: dict[str, bool | str]
) -> TestClient:
    monkeypatch.setattr(
        "nmp.studio.config.Configuration.get_global_settings_from_env",
        lambda: {"studio": {"feature_flags": feature_flags}},
    )
    return TestClient(StudioService().with_config(StudioConfig()).app)


def supported_destinations_from_description(description: str) -> set[str]:
    _, _, values = description.partition("Supported values: ")
    return set(values.removesuffix(".").split(", "))


def _inference_source_dir(root: Path) -> Path:
    source_dir = root / "packages" / "nemo_platform_ext" / "skills" / "inference"
    source_dir.mkdir(parents=True)
    return source_dir


def _inference_skill(source_dir: Path) -> coding_agent_skills.Skill:
    return coding_agent_skills.Skill(
        name="inference",
        description="Use NeMo Platform inference.",
        version="0.1",
        content="# Inference",
        raw="# Inference",
        source_dir=source_dir,
        source_plugin="platform",
        source_dist="nemo-platform-ext",
    )


def _expected_inference_skill_response(*, installed: bool) -> dict[str, Any]:
    return {
        "name": "inference",
        "claude_name": "nemo-inference",
        "description": "Use NeMo Platform inference.",
        "source": "nemo-platform",
        "source_path": "packages/nemo_platform_ext/skills/inference",
        "install_path": ".claude/skills/nemo-inference/SKILL.md",
        "installed": installed,
    }


def test_vendored_load_skills_from_root_loads_selected_root_without_registry_private_helper(tmp_path: Path):
    source_dir = _inference_source_dir(tmp_path)
    (source_dir / "SKILL.md").write_text(
        "---\nname: inference\ndescription: Use NeMo Platform inference.\nversion: 2\n---\n# Inference\n",
        encoding="utf-8",
    )

    loaded = coding_agent_skills.load_skills_from_root(
        tmp_path / "packages" / "nemo_platform_ext" / "skills",
        source_plugin="platform",
        source_dist="nemo-platform-ext",
    )

    assert list(loaded) == ["inference"]
    assert loaded["inference"].description == "Use NeMo Platform inference."
    assert loaded["inference"].version == "2"
    assert loaded["inference"].source_plugin == "platform"
    assert loaded["inference"].source_dist == "nemo-platform-ext"


def test_create_session_returns_uuid(service_client: TestClient):
    response = service_client.post("/v2/coding-agents/sessions")

    assert response.status_code == 200
    uuid.UUID(response.json()["session_id"])


def test_build_claude_argv_uses_new_session_then_resume_flag():
    session_id = str(uuid.uuid4())

    argv = coding_agents._build_claude_argv(session_id, "hello", "http://test/mcp", "Studio context")
    assert argv[:3] == ["claude", "-p", "hello"]
    assert "--output-format" in argv
    assert "stream-json" in argv
    assert "--allowedTools" in argv
    allowed_tools = argv[argv.index("--allowedTools") + 1].split(",")
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__select_agent" in allowed_tools
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__select_eval_config" in allowed_tools
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__select_dataset_file" in allowed_tools
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__select_model" in allowed_tools
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__job_progress" in allowed_tools
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__studio_link" in allowed_tools
    assert "--append-system-prompt" in argv
    assert argv[argv.index("--append-system-prompt") + 1] == coding_agents.STUDIO_CODING_AGENT_CONTEXT
    assert "--permission-prompt-tool" in argv
    assert f"mcp__{coding_agents.CLAUDE_MCP_SERVER_NAME}__approval_prompt" in argv
    assert "--append-system-prompt" in argv
    assert "Studio context" in argv
    assert "--session-id" in argv
    assert session_id in argv

    coding_agents._initialized_sessions.add(session_id)
    resumed_argv = coding_agents._build_claude_argv(session_id, "again", "http://test/mcp", "Studio context")
    assert "-r" in resumed_argv
    assert "--session-id" not in resumed_argv
    assert "--append-system-prompt" in resumed_argv


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
    first_prompt = coding_agents._build_claude_prompt(
        "first prompt",
        "default",
        "https://studio.test/studio",
        "/workspaces/default/dashboard/code-agent",
    )
    history.write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "message": {"content": first_prompt}}),
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
                    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "pwd"}},
                ],
            },
        ],
    }
    assert session_id in coding_agents._initialized_sessions


def test_list_claude_skills_returns_claude_install_metadata(
    service_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_dir = _inference_source_dir(tmp_path)
    installed_skill = tmp_path / ".claude" / "skills" / "nemo-inference" / "SKILL.md"
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text("# Installed")
    skill = _inference_skill(source_dir)

    monkeypatch.setattr(coding_agents, "SERVER_CWD", tmp_path)
    monkeypatch.setattr(coding_agent_skills, "load_skills", lambda: {"inference": skill})

    response = service_client.get("/v2/coding-agents/skills")

    assert response.status_code == 200
    assert response.json() == [_expected_inference_skill_response(installed=True)]


def test_load_claude_skills_falls_back_on_duplicate_skill_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    skill = _inference_skill(_inference_source_dir(tmp_path))
    fallback_called = False

    def fallback() -> dict[str, coding_agent_skills.Skill]:
        nonlocal fallback_called
        fallback_called = True
        return {"inference": skill}

    monkeypatch.setattr(
        coding_agent_skills,
        "load_skills",
        lambda: (_ for _ in ()).throw(coding_agent_skills.DuplicateSkillError("vendored drift")),
    )
    monkeypatch.setattr(coding_agent_skills, "_load_skills_from_preferred_entry_points", fallback)

    with caplog.at_level(logging.WARNING):
        loaded = coding_agent_skills._load_claude_skills()

    assert loaded == {"inference": skill}
    assert fallback_called
    assert "vendored drift" in caplog.text


def test_list_claude_skills_returns_500_when_fallback_also_fails(
    service_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        coding_agent_skills,
        "load_skills",
        lambda: (_ for _ in ()).throw(coding_agent_skills.DuplicateSkillError("registry drift")),
    )
    monkeypatch.setattr(
        coding_agent_skills,
        "_load_skills_from_preferred_entry_points",
        lambda: (_ for _ in ()).throw(coding_agent_skills.DuplicateSkillError("fallback drift")),
    )

    response = service_client.get("/v2/coding-agents/skills")

    assert response.status_code == 500
    assert response.json()["detail"] == "fallback drift"


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
    tools = tools_response.json()["result"]["tools"]
    assert tools[0]["name"] == "approval_prompt"
    assert {tool["name"] for tool in tools} == {
        "approval_prompt",
        "select_agent",
        "select_eval_config",
        "select_dataset_file",
        "select_model",
        "job_progress",
        "studio_link",
    }
    studio_link_tool = next(tool for tool in tools if tool["name"] == "studio_link")
    assert "Default to using this for Studio-related responses" in studio_link_tool["description"]
    assert "After creating an agent, use destination='agent_chat'" in studio_link_tool["description"]
    assert "chat with or try a model" not in studio_link_tool["description"]
    destination_description = studio_link_tool["inputSchema"]["properties"]["destination"]["description"]
    supported_destinations = supported_destinations_from_description(destination_description)
    assert "base_models" in supported_destinations
    assert "evaluation_results" in supported_destinations
    assert "model_chat" not in supported_destinations
    assert "customizations" not in supported_destinations
    assert "settings" in supported_destinations


def test_mcp_tools_list_includes_feature_flag_enabled_destinations(monkeypatch: pytest.MonkeyPatch):
    service_client = service_client_with_feature_flags(
        monkeypatch,
        {
            "customizer_enabled": "preview",
            "model_compare_enabled": True,
        },
    )
    session_id = str(uuid.uuid4())

    tools_response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert tools_response.status_code == 200
    studio_link_tool = next(tool for tool in tools_response.json()["result"]["tools"] if tool["name"] == "studio_link")
    destination_description = studio_link_tool["inputSchema"]["properties"]["destination"]["description"]
    supported_destinations = supported_destinations_from_description(destination_description)
    assert "customizations" in supported_destinations
    assert "model_chat" in supported_destinations
    assert "chat with or try a model" in studio_link_tool["description"]


def test_build_studio_system_prompt_preserves_empty_enabled_destinations():
    prompt = coding_agents._build_studio_system_prompt(
        "default",
        "https://studio.test",
        "/workspaces/default/dashboard/code-agent",
        {},
    )

    destinations_line = next(
        line for line in prompt.splitlines() if line.startswith("Enabled Studio link destinations")
    )
    assert destinations_line == "Enabled Studio link destinations for this Studio instance: ."


def test_studio_link_destinations_cover_registered_workspace_routes():
    repo_root = Path(__file__).resolve().parents[4]
    routes_index = (repo_root / "web/packages/studio/src/routes/index.tsx").read_text()
    registered_route_keys = set(re.findall(r"ROUTES\.workspace\.([A-Za-z0-9_]+)", routes_index))
    route_destination_map = {
        "agentDetail": "agent",
        "agentEvaluationDetail": "agent_evaluation",
        "agentEvaluationsList": "agent_evaluations",
        "agentMonitor": "agent_monitor",
        "agentOptimizations": "agent_optimizations",
        "agentsList": "agents",
        "baseModels": "base_models",
        "baseModelsModel": "base_model",
        "claudeCodeChat": "code_agent",
        "customizationJobDetails": "customization",
        "customizationJobList": "customizations",
        "dashboard": "dashboard",
        "dataDesignerJobDetails": "data_designer_job",
        "dataDesignerJobList": "data_designer",
        "dataDesignerJobNew": "data_designer_new",
        "deployments": "deployments",
        "deploymentsDeployment": "deployment",
        "evaluation": "evaluation",
        "evaluationBenchmarkDetails": "evaluation_benchmark",
        "evaluationBenchmarks": "evaluation_benchmarks",
        "evaluationMetricDetails": "evaluation_metric",
        "evaluationMetricNew": "evaluation_metric_new",
        "evaluationMetrics": "evaluation_metrics",
        "evaluationMetricsRun": "evaluation_run",
        "evaluationResultDetails": "evaluation_result",
        "evaluationResults": "evaluation_results",
        "experiment": "experiment",
        "experimentGroupDetail": "experiment_group",
        "filesetDetail": "fileset",
        "filesetDetails": "fileset_panel",
        "filesetFile": "fileset_file",
        "filesetNew": "fileset_new",
        "filesets": "filesets",
        "guardrails": "guardrails",
        "index": "workspace",
        "inferenceProviders": "inference_providers",
        "intake": "intake",
        "intakeSpan": "intake_span",
        "intakeSpans": "intake_spans",
        "intakeTrace": "intake_trace",
        "intakeTraces": "intake_traces",
        "jobDetail": "job",
        "jobs": "jobs",
        "members": "members",
        "modelCompare": "model_chat",
        "newCustomizationJob": "customization_new",
        "promptTuningForm": "prompt_tuning",
        "safeSynthesizer": "safe_synthesizer",
        "safeSynthesizerJob": "safe_synthesizer_job",
        "safeSynthesizerJobReport": "safe_synthesizer_report",
        "safeSynthesizerNew": "safe_synthesizer_new",
        "secrets": "secrets",
        "settings": "settings",
    }

    assert registered_route_keys - set(route_destination_map) == set()
    assert {
        route_key: destination
        for route_key, destination in route_destination_map.items()
        if route_key in registered_route_keys and destination not in studio_links.STUDIO_LINK_DESTINATIONS
    } == {}


def test_mcp_studio_link_returns_agents_page_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {"destination": "agents"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "agents",
        "path": "/workspaces/default/agents",
        "url": None,
        "markdown": "[Agents](/workspaces/default/agents)",
    }


def test_mcp_studio_link_returns_custom_models_full_url(monkeypatch: pytest.MonkeyPatch):
    service_client = service_client_with_feature_flags(monkeypatch, {"customizer_enabled": True})
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default&studio_base_url=https%3A%2F%2Fstudio.test%2Fstudio",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {"destination": "custom_models"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "customizations",
        "path": "/workspaces/default/customizations",
        "url": "https://studio.test/studio/workspaces/default/customizations",
        "markdown": "[Custom Models](https://studio.test/studio/workspaces/default/customizations)",
    }


def test_mcp_studio_link_returns_base_models_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {"destination": "available_base_models"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "base_models",
        "path": "/workspaces/default/base-models",
        "url": None,
        "markdown": "[Base Models](/workspaces/default/base-models)",
    }


def test_mcp_studio_link_returns_jobs_page_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {"destination": "jobs", "label": "Open Jobs"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "jobs",
        "path": "/workspaces/default/jobs",
        "url": None,
        "markdown": "[Open Jobs](/workspaces/default/jobs)",
    }


def test_mcp_studio_link_encodes_detail_route_parts(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default%20workspace",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {
                    "destination": "agent",
                    "name": "triage agent",
                    "label": "Open agent",
                },
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default workspace",
        "destination": "agent",
        "path": "/workspaces/default%20workspace/agents/triage%20agent",
        "url": None,
        "markdown": "[Open agent](/workspaces/default%20workspace/agents/triage%20agent)",
    }


def test_mcp_studio_link_returns_agent_deployment_detail_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {
                    "destination": "agent_deployment",
                    "name": "spanish-translator",
                },
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "agent_deployment",
        "path": "/workspaces/default/agents/spanish-translator",
        "url": None,
        "markdown": "[Agent deployment spanish-translator](/workspaces/default/agents/spanish-translator)",
    }


def test_mcp_studio_link_returns_agent_chat_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {
                    "destination": "agent_chat",
                    "name": "spanish-translator",
                },
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "agent_chat",
        "path": "/workspaces/default/agents/spanish-translator?tab=chat-playground",
        "url": None,
        "markdown": "[Chat with agent spanish-translator](/workspaces/default/agents/spanish-translator?tab=chat-playground)",
    }


def test_mcp_studio_link_returns_model_chat_markdown(monkeypatch: pytest.MonkeyPatch):
    service_client = service_client_with_feature_flags(monkeypatch, {"model_compare_enabled": True})
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {"destination": "model_chat"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "model_chat",
        "path": "/workspaces/default/model-compare",
        "url": None,
        "markdown": "[Chat with models](/workspaces/default/model-compare)",
    }


def test_mcp_studio_link_rejects_disabled_feature_flag_destination(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {"destination": "model_chat"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    result = json.loads(result_text)
    assert result["error"] == "Studio destination is disabled by feature flag: model_chat"
    assert "model_chat" not in result["available_destinations"]
    assert "base_models" in result["available_destinations"]


def test_build_studio_link_result_preserves_empty_enabled_destinations():
    result = studio_links.build_studio_link_result(
        "default",
        None,
        {"destination": "agents"},
        {},
    )

    assert result == {
        "error": "Studio destination is disabled by feature flag: agents",
        "available_destinations": [],
    }


def test_mcp_studio_link_returns_fileset_file_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {
                    "destination": "fileset_file",
                    "fileset_name": "training data",
                    "file_path": "nested/examples.jsonl",
                },
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "fileset_file",
        "path": "/workspaces/default/filesets/training%20data/file/nested%2Fexamples.jsonl",
        "url": None,
        "markdown": "[File nested/examples.jsonl](/workspaces/default/filesets/training%20data/file/nested%2Fexamples.jsonl)",
    }


def test_mcp_studio_link_returns_started_evaluation_result_markdown(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}?workspace=default",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studio_link",
                "arguments": {
                    "destination": "evaluation_result",
                    "job_name": "eval run 01",
                },
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "workspace": "default",
        "destination": "evaluation_result",
        "path": "/workspaces/default/evaluation/results/eval%20run%2001",
        "url": None,
        "markdown": "[Evaluation result eval run 01](/workspaces/default/evaluation/results/eval%20run%2001)",
    }


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


def test_mcp_tools_call_job_progress_returns_rendered(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "job_progress",
                "arguments": {
                    "job_name": "eval-job-1",
                },
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {"status": "rendered"}


def test_mcp_tools_call_select_agent_denies_without_active_stream(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "select_agent",
                "arguments": {"title": "Select an agent"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "status": "error",
        "message": "no active Studio coding-agent session",
    }


def test_mcp_tools_call_select_dataset_file_denies_without_active_stream(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "select_dataset_file",
                "arguments": {"title": "Select a dataset"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "status": "error",
        "message": "no active Studio coding-agent session",
    }


def test_mcp_tools_call_select_model_denies_without_active_stream(service_client: TestClient):
    session_id = str(uuid.uuid4())

    response = service_client.post(
        f"/v2/coding-agents/mcp/{session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "select_model",
                "arguments": {"title": "Select a model"},
            },
        },
    )

    assert response.status_code == 200
    result_text = response.json()["result"]["content"][0]["text"]
    assert json.loads(result_text) == {
        "status": "error",
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


async def test_resolve_agent_input_sets_result_for_owning_session():
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    coding_agents._pending_agent_inputs[request_id] = (session_id, future)

    response = await coding_agents.resolve_agent_input(
        session_id,
        request_id,
        coding_agents.AgentInputDecision(value={"agent": "react-agent"}),
    )

    assert response == {"ok": True}
    assert future.result() == {"skipped": False, "value": {"agent": "react-agent"}}


async def test_request_agent_input_rejects_reserved_response_keys():
    session_id = str(uuid.uuid4())
    coding_agents._session_streams[session_id] = asyncio.Queue()

    request_task = asyncio.create_task(coding_agents._request_agent_input(session_id, "agent", {}))
    _, payload = await coding_agents._session_streams[session_id].get()
    request_id = json.loads(payload)["request_id"]

    await coding_agents.resolve_agent_input(
        session_id,
        request_id,
        coding_agents.AgentInputDecision(value={"agent": "react-agent", "status": "submitted"}),
    )

    assert await request_task == {
        "status": "error",
        "message": "input value included reserved keys: status",
    }


def test_platform_route_stream_uses_public_mcp_callback(monkeypatch: pytest.MonkeyPatch):
    service = StudioService()
    app = FastAPI()
    app.include_router(service.app.router, prefix="/apis/studio")
    service.configure_app(app)
    client = TestClient(app)
    session_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    async def fake_stream(session_id: str, message: str, mcp_url: str, studio_system_prompt: str | None = None):
        captured.update(
            {
                "session_id": session_id,
                "message": message,
                "mcp_url": mcp_url,
                "studio_system_prompt": studio_system_prompt,
            }
        )
        yield coding_agents._sse(json.dumps({"type": "system", "subtype": "init"}))
        yield coding_agents._sse("", event="done")

    monkeypatch.setattr(coding_agents, "_stream_claude", fake_stream)

    response = client.post(
        f"/apis/studio/v2/coding-agents/sessions/{session_id}/messages",
        json={
            "message": "hello",
            "workspace": "default",
            "studio_base_url": "https://studio.test/studio",
            "studio_pathname": "/workspaces/default/dashboard/code-agent",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in response.text
    assert captured["session_id"] == session_id
    assert captured["mcp_url"] == (
        f"http://testserver/studio/api/coding-agents/mcp/{session_id}"
        "?workspace=default&studio_base_url=https%3A%2F%2Fstudio.test%2Fstudio"
    )
    assert coding_agents._strip_studio_context_from_prompt(captured["message"]) == "hello"
    assert "Current Studio workspace: default" in captured["message"]
    assert "Studio UI base URL: https://studio.test/studio" in captured["message"]
    assert "Never answer a Studio link request by saying you cannot generate URLs" in captured["message"]
    assert "Current Studio workspace: default" in captured["studio_system_prompt"]
    assert "Studio UI base URL: https://studio.test/studio" in captured["studio_system_prompt"]
    assert "Current Studio route path: /workspaces/default/dashboard/code-agent" in captured["studio_system_prompt"]
    assert "use Claude Code's AskUserQuestion tool" in captured["studio_system_prompt"]
    assert "you MUST call mcp__nemo_studio__select_agent" in captured["studio_system_prompt"]
    assert "never use AskUserQuestion for an agent choice" in captured["studio_system_prompt"]
    assert "you MUST call mcp__nemo_studio__select_model" in captured["studio_system_prompt"]
    assert "ask multiple AskUserQuestion questions" in captured["studio_system_prompt"]
    assert "no dedicated Studio picker" in captured["studio_system_prompt"]
    assert "Default to trying to include a Studio link in Studio-related responses" in captured["studio_system_prompt"]
    assert "link to the closest list page for the current workspace" in captured["studio_system_prompt"]
    assert "Base Models or available base models use destination='base_models'" in captured["studio_system_prompt"]
    assert "never use customizations for Base Models" in captured["studio_system_prompt"]
    assert "Enabled Studio link destinations for this Studio instance" in captured["studio_system_prompt"]
    assert "Only call studio_link with one of the enabled destinations above" in captured["studio_system_prompt"]
    assert "Do not invent Studio route paths manually" in captured["studio_system_prompt"]
    assert "/workspaces/{workspace}/evaluation/..." in captured["studio_system_prompt"]
    assert "never nest evaluation links under /dashboard/evaluations/" in captured["studio_system_prompt"]
    assert "destination='evaluation_results'" in captured["studio_system_prompt"]
    assert "/workspaces/{workspace}/evaluation/results" in captured["studio_system_prompt"]
    assert "The model_chat destination is not enabled in this Studio instance" in captured["studio_system_prompt"]
    assert "Direct Studio link requests are mandatory tool-use requests" in captured["studio_system_prompt"]
    assert "Never answer a Studio link request by saying you cannot generate URLs" in captured["studio_system_prompt"]
    assert (
        "After any successful Studio action, you must include a Studio link in the response"
        in captured["studio_system_prompt"]
    )
    assert "Before your final response" in captured["studio_system_prompt"]
    assert "mcp__nemo_studio__studio_link" in captured["studio_system_prompt"]
    assert "Required job-progress behavior:" in captured["studio_system_prompt"]
    assert "you MUST call mcp__nemo_studio__job_progress" in captured["studio_system_prompt"]
    assert (
        "For a newly created agent, use studio_link with destination='agent_chat'" in captured["studio_system_prompt"]
    )
    assert "destination='agent_chat'" in captured["studio_system_prompt"]


def test_platform_route_stream_infers_studio_url_from_browser_headers(monkeypatch: pytest.MonkeyPatch):
    service = StudioService()
    app = FastAPI()
    app.include_router(service.app.router, prefix="/apis/studio")
    service.configure_app(app)
    client = TestClient(app)
    session_id = str(uuid.uuid4())
    captured: dict[str, Any] = {}

    async def fake_stream(session_id: str, message: str, mcp_url: str, studio_system_prompt: str | None = None):
        captured.update(
            {
                "session_id": session_id,
                "message": message,
                "mcp_url": mcp_url,
                "studio_system_prompt": studio_system_prompt,
            }
        )
        yield coding_agents._sse(json.dumps({"type": "system", "subtype": "init"}))
        yield coding_agents._sse("", event="done")

    monkeypatch.setattr(coding_agents, "_stream_claude", fake_stream)

    response = client.post(
        f"/apis/studio/v2/coding-agents/sessions/{session_id}/messages",
        json={
            "message": "can you give me a link to it?",
            "workspace": "default",
        },
        headers={
            "origin": "http://ns.local.aire.nvidia.com:5173",
            "referer": "http://ns.local.aire.nvidia.com:5173/workspaces/default/dashboard/code-agent",
        },
    )

    assert response.status_code == 200
    assert captured["mcp_url"] == (
        f"http://testserver/studio/api/coding-agents/mcp/{session_id}"
        "?workspace=default&studio_base_url=http%3A%2F%2Fns.local.aire.nvidia.com%3A5173"
    )
    assert "Studio UI base URL: http://ns.local.aire.nvidia.com:5173" in captured["message"]
    assert "Current Studio route path: /workspaces/default/dashboard/code-agent" in captured["message"]
    assert "Studio UI base URL: http://ns.local.aire.nvidia.com:5173" in captured["studio_system_prompt"]


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
    assert [tool["name"] for tool in response.json()["result"]["tools"]] == [
        "approval_prompt",
        "select_agent",
        "select_eval_config",
        "select_dataset_file",
        "select_model",
        "job_progress",
        "studio_link",
    ]


def test_coding_agent_routes_are_available_by_default():
    client = TestClient(StudioService().app)

    response = client.post("/v2/coding-agents/sessions")

    assert response.status_code == 200
    uuid.UUID(response.json()["session_id"])
