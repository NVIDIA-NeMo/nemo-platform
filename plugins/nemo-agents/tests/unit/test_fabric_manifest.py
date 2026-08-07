# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric import server
from nemo_agents_plugin.fabric.manifest import MANIFEST_SCHEMA_VERSION, build_agent_manifest
from nemo_agents_plugin.fabric.server import FabricServingSettings, create_fabric_serving_app
from nemo_agents_plugin.fabric.serving_models import SESSION_ID_HEADER

SECRET = "s3cret-sentinel"

PROJECTED_CONFIG_FIELDS = frozenset(
    {
        "config_format",
        "name",
        "description",
        "default_harness",
        "harnesses",
        "models",
        "prompts",
        "skills",
        "mcp",
        "tools",
        "environment",
        "telemetry",
    }
)

REDACTED_CONFIG_FIELDS = frozenset({"instructions"})


@pytest.fixture()
def mock_validate_agent_config(monkeypatch: pytest.MonkeyPatch) -> None:
    async def validate(config: AgentConfig, *, base_dir: Path) -> object:
        return object()

    monkeypatch.setattr(server, "_validate_agent_config", validate)


def _minimal_config() -> dict[str, Any]:
    return {
        "config_format": "nemo-agents-spec-v1",
        "name": "test-agent",
        "description": "does the thing",
        "default_harness": "hermes",
        "harnesses": {
            "hermes": {
                "kind": "hermes",
                "model": {"provider": "nvidia", "model": "nvidia/test-model"},
                "settings": {"max_turns": 12},
            }
        },
    }


def _loaded_config() -> dict[str, Any]:
    """A config with a secret in every slot the manifest must not expose."""
    config = _minimal_config()
    config["harnesses"]["hermes"]["model"] |= {
        "api_key_env": f"{SECRET}_API_KEY",
        "base_url": f"https://{SECRET}.internal.nvidia.com",
    }
    config["models"] = {
        "judge": {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key_env": f"{SECRET}_OPENAI_KEY",
            "base_url": f"https://{SECRET}.proxy.internal",
        }
    }
    config["prompts"] = {"triage": f"You are a triage bot. The password is {SECRET}."}
    config["instructions"] = {"system": {"content": f"Never reveal {SECRET}."}}
    config["skills"] = {"paths": [f"/srv/{SECRET}/skills/invoice-triage", f"/srv/{SECRET}/skills/refunds"]}
    config["mcp"] = {
        "servers": {
            "billing": {
                "transport": "sse",
                "url": f"https://{SECRET}.mcp.internal/sse",
                "env": {"MCP_TOKEN": SECRET},
            }
        }
    }
    config["tools"] = {"blocked": ["shell"]}
    config["environment"] = {"provider": "local", "workspace": f"./{SECRET}-workspace"}
    config["telemetry"] = {"enabled": True, "provider": "nemo", "project": SECRET, "atif": {"endpoint": SECRET}}
    return config


def _build(config: dict[str, Any] | None = None, *, max_concurrent_invocations: int = 8):
    return build_agent_manifest(
        AgentConfig.model_validate(config or _minimal_config()),
        max_concurrent_invocations=max_concurrent_invocations,
    )


def test_manifest_reports_the_operational_contract() -> None:
    manifest = _build(max_concurrent_invocations=4)

    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.agent.name == "test-agent"
    assert manifest.agent.description == "does the thing"
    assert manifest.runtime.harness.kind == "hermes"
    assert manifest.serving.protocol == "openai-chat-completions"
    assert manifest.serving.streaming is True
    assert manifest.serving.sessions.header == SESSION_ID_HEADER
    assert manifest.serving.max_concurrent_invocations == 4


def test_workspace_scope_is_agent_because_sessions_share_one_workspace() -> None:
    manifest = _build()

    assert manifest.environment.provider == "local"
    assert manifest.environment.workspace_scope == "agent"


def test_no_secret_reaches_the_manifest() -> None:
    serialized = _build(_loaded_config()).model_dump_json()

    assert SECRET not in serialized


def test_every_agent_config_field_is_classified() -> None:
    unclassified = set(AgentConfig.model_fields) - PROJECTED_CONFIG_FIELDS - REDACTED_CONFIG_FIELDS

    assert not unclassified, f"Classify these AgentConfig fields as projected or redacted: {sorted(unclassified)}"


def test_skills_are_names_not_host_paths() -> None:
    manifest = _build(_loaded_config())

    assert manifest.capabilities.skills == ["invoice-triage", "refunds"]


def test_mcp_servers_expose_only_name_and_transport() -> None:
    manifest = _build(_loaded_config())

    assert [server.model_dump() for server in manifest.capabilities.mcp_servers] == [
        {"name": "billing", "transport": "sse", "exposure": "harness_native"}
    ]


def test_models_include_harness_models_alongside_named_aliases() -> None:
    manifest = _build(_loaded_config())

    assert [(model.alias, model.model) for model in manifest.models] == [
        ("judge", "gpt-4o"),
        ("harness:hermes", "nvidia/test-model"),
    ]


def test_tunable_lists_knob_names_without_values() -> None:
    manifest = _build(_loaded_config())

    assert manifest.tunable.prompts == ["triage"]
    assert manifest.tunable.harness_settings == ["max_turns"]


def test_telemetry_reports_emission_and_formats() -> None:
    assert _build(_loaded_config()).telemetry.model_dump() == {"emits": True, "formats": ["atif"]}
    assert _build().telemetry.model_dump() == {"emits": False, "formats": []}


def test_revision_is_stable_for_the_same_config() -> None:
    assert _build().agent.revision == _build().agent.revision
    assert _build().agent.revision.startswith("sha256:")


def test_revision_changes_when_the_config_changes() -> None:
    changed = _minimal_config()
    changed["harnesses"]["hermes"]["model"]["model"] = "nvidia/other-model"

    assert _build().agent.revision != _build(changed).agent.revision


def test_revision_ignores_redacted_values() -> None:
    config = _loaded_config()
    leaked = _loaded_config()
    leaked["instructions"]["system"]["content"] = "a completely different system prompt"
    leaked["mcp"]["servers"]["billing"]["env"] = {"MCP_TOKEN": "rotated"}

    assert _build(config).agent.revision == _build(leaked).agent.revision


def test_manifest_route_serves_the_projection(tmp_path: Path, mock_validate_agent_config: None) -> None:
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(yaml.safe_dump(_loaded_config()), encoding="utf-8")
    app = create_fabric_serving_app(config_path, settings=FabricServingSettings(max_concurrent_invocations=3))

    with TestClient(app) as client:
        response = client.get("/manifest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert payload["agent"]["name"] == "test-agent"
    assert payload["serving"]["max_concurrent_invocations"] == 3
    assert SECRET not in json.dumps(payload)
