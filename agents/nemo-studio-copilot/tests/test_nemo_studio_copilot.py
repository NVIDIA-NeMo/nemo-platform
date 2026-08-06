# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nemo_agents_plugin.agent_config import load_agent_config
from nemo_agents_plugin.fabric.translator import translate_agent_config
from nemo_studio_copilot import register
from nemo_studio_copilot.mcp_server import create_server

AGENT_ROOT = Path(__file__).parents[1]
SPEC_ROOT = AGENT_ROOT.parent / "nemo-studio-copilot-spec"


def test_agent_config_translates_to_fabric_deepagents() -> None:
    config = load_agent_config(AGENT_ROOT / "agent.yaml")
    translated = translate_agent_config(config)

    assert config.default_harness == "deepagents"
    assert config.models["default"].model == "nvidia-nemotron-3-super-120b-a12b"
    assert translated.harness.adapter_id == "nvidia.fabric.langchain.deepagents"
    assert translated.models["default"].provider == "nvidia"


def test_canonical_registration_config_translates_to_same_runtime() -> None:
    source = translate_agent_config(load_agent_config(AGENT_ROOT / "agent.yaml"))
    registered = translate_agent_config(load_agent_config(SPEC_ROOT / "agent.yaml"))

    assert registered.harness == source.harness
    assert registered.models == source.models
    assert registered.instructions == source.instructions
    assert registered.mcp == source.mcp


def test_every_configured_skill_is_packaged() -> None:
    config = load_agent_config(AGENT_ROOT / "agent.yaml")

    assert config.skills is not None
    assert len(config.skills.paths) == 9
    for skill_path in config.skills.paths:
        skill_file = AGENT_ROOT / skill_path / "SKILL.md"
        assert skill_file.is_file(), skill_file
        assert skill_file.read_text(encoding="utf-8").startswith("---\n")

    registered = load_agent_config(SPEC_ROOT / "agent.yaml")
    assert registered.skills is not None
    for skill_path in registered.skills.paths:
        assert (SPEC_ROOT / skill_path / "SKILL.md").is_file()


def test_mcp_server_exposes_expected_tools() -> None:
    tools = asyncio.run(create_server().list_tools())

    assert {tool.name for tool in tools} == {
        "nemo_api",
        "check_status",
        "select_agent",
        "select_model",
        "select_dataset_file",
        "select_eval_config",
        "job_progress",
        "studio_link",
        "ask_user_question",
    }


def test_read_only_nemo_api_calls_sdk_without_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = SimpleNamespace(list=lambda: [SimpleNamespace(name="default")])
    monkeypatch.setattr(register, "_client", SimpleNamespace(workspaces=resource))

    response = json.loads(register.nemo_api("workspaces", "list"))

    assert response == ["namespace(name='default')"]


def test_mutating_nemo_api_requires_studio_session(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def create(**_kwargs: object) -> object:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(register, "_client", SimpleNamespace(workspaces=SimpleNamespace(create=create)))

    response = register.nemo_api("workspaces", "create", '{"name": "demo"}')

    assert response.startswith("Denied:")
    assert called is False


def test_mutating_nemo_api_uses_studio_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "90a877d5-19f6-49a8-bf09-d0020ae0833a"
    approvals: list[tuple[str, str, dict[str, object]]] = []

    def approve(session: str, tool_name: str, arguments: dict[str, object], **_kwargs: object) -> dict[str, str]:
        approvals.append((session, tool_name, arguments))
        return {"behavior": "allow"}

    resource = SimpleNamespace(create=lambda **kwargs: kwargs)
    monkeypatch.setattr(register, "_client", SimpleNamespace(workspaces=resource))
    monkeypatch.setattr(register, "_call_studio_tool", approve)

    response = json.loads(register.nemo_api("workspaces", "create", '{"name": "demo"}', studio_session_id=session_id))

    assert response == {"name": "demo"}
    assert approvals[0][0:2] == (session_id, "approval_prompt")


def test_nemo_api_rejects_non_object_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(register, "_client", SimpleNamespace(workspaces=SimpleNamespace(list=lambda: [])))

    response = register.nemo_api("workspaces", "list", '["not", "an", "object"]')

    assert response == "Error: ValueError: params must decode to a JSON object"


def test_studio_callback_url_validates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_BASE_URL", "http://platform:8080")

    with pytest.raises(ValueError, match="valid Studio session"):
        register._studio_callback_url("../../bad")


def test_studio_callback_url_uses_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_BASE_URL", "http://platform:8080")
    session_id = "90a877d5-19f6-49a8-bf09-d0020ae0833a"

    url = register._studio_callback_url(session_id, workspace="demo")

    assert url == f"http://platform:8080/studio/api/copilot/mcp/{session_id}?workspace=demo"


def test_ask_user_question_rejects_invalid_payload() -> None:
    response = register.ask_user_question("90a877d5-19f6-49a8-bf09-d0020ae0833a", "{}")

    assert response == "Error: `questions` must be a non-empty JSON array of question objects."
