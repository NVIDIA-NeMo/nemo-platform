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
EVAL_DATA_PATH = AGENT_ROOT / "src/nemo_studio_copilot/nemo-studio-copilot-eval-data.json"

pytestmark = pytest.mark.unit

EvalCall = tuple[str, str, str | None]
EVAL_CASE_COVERAGE: dict[str, tuple[str, tuple[EvalCall, ...], list[object]]] = {
    "Show the details for the default workspace without making any changes.": (
        "details for the default workspace",
        (("workspaces", "retrieve", '{"name":"default"}'),),
        [{"name": "default", "description": "Default workspace"}],
    ),
    "List all workspaces on the platform": (
        "list of workspaces",
        (("workspaces", "list", None),),
        [[{"name": "default"}, {"name": "research"}]],
    ),
    "List the available models and inference providers using the platform API.": (
        "list of available models and inference providers",
        (("models", "list", None), ("inference.providers", "list", None)),
        [[{"name": "model-a"}], [{"name": "provider-a"}]],
    ),
}


def _load_eval_cases() -> list[dict[str, str]]:
    raw_cases = json.loads(EVAL_DATA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw_cases, list)
    cases: list[dict[str, str]] = []
    for raw_case in raw_cases:
        assert isinstance(raw_case, dict)
        input_message = raw_case.get("input_message")
        expected_output = raw_case.get("expected_output")
        assert isinstance(input_message, str)
        assert isinstance(expected_output, str)
        cases.append({"input_message": input_message, "expected_output": expected_output})
    return cases


EVAL_CASES = _load_eval_cases()


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
    monkeypatch.setattr(register, "_clients", {"default": SimpleNamespace(workspaces=resource)})

    response = json.loads(register.nemo_api("workspaces", "list", workspace="default"))

    assert response == ["namespace(name='default')"]


def test_every_eval_case_has_deterministic_coverage() -> None:
    assert len(EVAL_CASES) == 3
    assert {case["input_message"] for case in EVAL_CASES} == EVAL_CASE_COVERAGE.keys()


@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda case: case["input_message"])
def test_eval_case_uses_expected_read_only_tool_paths(monkeypatch: pytest.MonkeyPatch, case: dict[str, str]) -> None:
    expected_output, calls, expected_results = EVAL_CASE_COVERAGE[case["input_message"]]
    assert case["expected_output"] == expected_output

    client = SimpleNamespace(
        workspaces=SimpleNamespace(
            retrieve=lambda name: {"name": name, "description": "Default workspace"},
            list=lambda: [{"name": "default"}, {"name": "research"}],
        ),
        models=SimpleNamespace(list=lambda: [{"name": "model-a"}]),
        inference=SimpleNamespace(providers=SimpleNamespace(list=lambda: [{"name": "provider-a"}])),
    )
    monkeypatch.setattr(register, "_clients", {"default": client})

    results = [
        json.loads(register.nemo_api(resource, action, params, workspace="default"))
        for resource, action, params in calls
    ]

    assert results == expected_results


def test_mutating_nemo_api_requires_studio_session(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def create(**_kwargs: object) -> object:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(register, "_clients", {"default": SimpleNamespace(workspaces=SimpleNamespace(create=create))})

    response = register.nemo_api("workspaces", "create", '{"name": "demo"}', workspace="default")

    assert response.startswith("Denied:")
    assert called is False


def test_mutating_nemo_api_uses_studio_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "90a877d5-19f6-49a8-bf09-d0020ae0833a"
    approvals: list[tuple[str, str, dict[str, object], dict[str, object]]] = []

    def approve(session: str, tool_name: str, arguments: dict[str, object], **kwargs: object) -> dict[str, str]:
        approvals.append((session, tool_name, arguments, kwargs))
        return {"behavior": "allow"}

    resource = SimpleNamespace(create=lambda **kwargs: kwargs)
    monkeypatch.setattr(register, "_clients", {"default": SimpleNamespace(workspaces=resource)})
    monkeypatch.setattr(register, "_call_studio_tool", approve)

    response = json.loads(
        register.nemo_api("workspaces", "create", '{"name": "demo"}', studio_session_id=session_id, workspace="default")
    )

    assert response == {"name": "demo"}
    assert approvals[0][0:2] == (session_id, "approval_prompt")
    assert approvals[0][2]["input"] == {
        "resource": "workspaces",
        "action": "create",
        "params": '{"name": "demo"}',
        "workspace": "default",
    }
    assert approvals[0][3]["workspace"] == "default"


def test_mutating_nemo_api_uses_edited_approved_input(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "90a877d5-19f6-49a8-bf09-d0020ae0833a"

    def approve(_session: str, _tool_name: str, arguments: dict[str, object], **_kwargs: object) -> dict[str, object]:
        input_value = arguments["input"]
        assert isinstance(input_value, dict)
        updated_input = dict(input_value)
        updated_input["params"] = '{"name": "approved"}'
        return {"behavior": "allow", "updatedInput": updated_input}

    resource = SimpleNamespace(create=lambda **kwargs: kwargs)
    monkeypatch.setattr(register, "_clients", {"default": SimpleNamespace(workspaces=resource)})
    monkeypatch.setattr(register, "_call_studio_tool", approve)

    response = json.loads(
        register.nemo_api(
            "workspaces", " CREATE ", '{"name": "original"}', studio_session_id=session_id, workspace="default"
        )
    )

    assert response == {"name": "approved"}


def test_mutating_nemo_api_validates_params_before_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    approval_requested = False

    def approve(*_args: object, **_kwargs: object) -> dict[str, str]:
        nonlocal approval_requested
        approval_requested = True
        return {"behavior": "allow"}

    monkeypatch.setattr(register, "_call_studio_tool", approve)

    response = register.nemo_api(
        "workspaces",
        "create",
        '["not", "an", "object"]',
        studio_session_id="90a877d5-19f6-49a8-bf09-d0020ae0833a",
        workspace="default",
    )

    assert response == "Error: ValueError: params must decode to a JSON object"
    assert approval_requested is False


def test_nemo_api_rejects_non_object_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(register, "_clients", {"default": SimpleNamespace(workspaces=SimpleNamespace(list=lambda: []))})

    response = register.nemo_api("workspaces", "list", '["not", "an", "object"]', workspace="default")

    assert response == "Error: ValueError: params must decode to a JSON object"


def test_nemo_api_uses_request_workspace_for_each_client(monkeypatch: pytest.MonkeyPatch) -> None:
    created_workspaces: list[str] = []

    def create_client(**kwargs: object) -> object:
        workspace = str(kwargs["workspace"])
        created_workspaces.append(workspace)
        return SimpleNamespace(models=SimpleNamespace(list=lambda: [workspace]))

    monkeypatch.setattr(register, "_clients", {})
    monkeypatch.setattr(register, "NeMoPlatform", create_client)

    first = json.loads(register.nemo_api("models", "list", workspace="first"))
    second = json.loads(register.nemo_api("models", "list", workspace="second"))

    assert first == ["first"]
    assert second == ["second"]
    assert created_workspaces == ["first", "second"]


def test_nemo_api_requires_request_workspace() -> None:
    response = register.nemo_api("models", "list")

    assert response == "Clarification required: which workspace should this operation use?"


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
