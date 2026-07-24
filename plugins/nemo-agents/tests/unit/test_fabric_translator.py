# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Platform agent config to FabricConfig translation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from nemo_agents_plugin.agent_config import AgentConfig, load_agent_config
from nemo_agents_plugin.fabric.translator import FabricTranslationError, translate_agent_config
from nemo_fabric import Fabric  # ty: ignore[unresolved-import]


def _example_yaml_config() -> dict[str, Any]:
    return {
        "config_format": "nemo-agents-spec-v1",
        "name": "example-agent",
        "description": "Example Agent",
        "default_harness": "hermes",
        "harnesses": {
            "hermes": {
                "kind": "hermes",
                "model": {
                    "provider": "nvidia",
                    "model": "nvidia/nemotron-3-nano-30b-a3b",
                    "api_key_env": "NVIDIA_API_KEY",
                    "temperature": 0.0,
                },
                "settings": {
                    "python_env": "HERMES_ADAPTER_PYTHON",
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "system_prompt": "You are a concise assistant.",
                },
            },
            "codex": {
                "kind": "codex",
                "settings": {
                    "sandbox": "workspace-write",
                },
            },
        },
        "models": {
            "default": {
                "provider": "openai",
                "model": "openai/gpt-5.4",
            },
        },
        "environment": {
            "workspace": "./workspace",
            "artifacts": "./artifacts",
        },
        "telemetry": {
            "enabled": False,
            "provider": "relay",
            "output_dir": "./artifacts/relay",
            "project": "example-agent",
            "atif": {
                "enabled": True,
                "filename_template": "trajectory-{session_id}.atif.json",
            },
            "atof": {
                "enabled": True,
                "filename": "events.atof.jsonl",
                "mode": "overwrite",
            },
        },
    }


class TestTranslateAgentConfig:
    def test_repository_example_uses_current_codex_and_isolated_hermes_adapters(self) -> None:
        example_path = Path(__file__).parents[2] / "examples/nemo-agent-config/agent.yaml"
        config = load_agent_config(example_path)

        codex_config = translate_agent_config(config, harness_name="codex")
        hermes_config = translate_agent_config(config, harness_name="hermes")

        assert codex_config.harness.adapter_id == "nvidia.fabric.codex"
        assert "skip_git_repo_check" not in codex_config.harness.settings
        assert hermes_config.harness.adapter_id == "nvidia.fabric.hermes"
        assert hermes_config.harness.settings["python_env"] == "HERMES_ADAPTER_PYTHON"

        fabric = Fabric()
        assert fabric.plan(codex_config, base_dir=example_path.parent).adapter.adapter_id == "nvidia.fabric.codex"
        assert fabric.plan(hermes_config, base_dir=example_path.parent).adapter.adapter_id == "nvidia.fabric.hermes"

    def test_translates_default_harness(self) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        fabric_config = translate_agent_config(config)

        assert fabric_config.metadata.name == "example-agent"
        assert fabric_config.metadata.description == "Example Agent"
        assert fabric_config.harness.adapter_id == "nvidia.fabric.hermes"
        assert fabric_config.harness.resolution == "preinstalled"
        assert fabric_config.harness.settings["python_env"] == "HERMES_ADAPTER_PYTHON"
        assert fabric_config.harness.settings["system_prompt"] == "You are a concise assistant."
        assert fabric_config.models["default"].provider == "nvidia"
        assert fabric_config.models["default"].model == "nvidia/nemotron-3-nano-30b-a3b"
        assert fabric_config.environment.provider == "local"
        assert fabric_config.environment.workspace == "./workspace"
        assert fabric_config.environment.artifacts == "./artifacts"
        assert fabric_config.relay is None

    def test_selected_harness_uses_default_model(self) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        fabric_config = translate_agent_config(config, harness_name="codex")

        assert fabric_config.harness.adapter_id == "nvidia.fabric.codex"
        assert fabric_config.harness.settings["sandbox"] == "workspace-write"
        assert fabric_config.models["default"].provider == "openai"
        assert fabric_config.models["default"].model == "openai/gpt-5.4"

    @pytest.mark.parametrize(
        ("kind", "adapter_id"),
        [
            ("claude", "nvidia.fabric.claude"),
            ("codex", "nvidia.fabric.codex"),
            ("deepagents", "nvidia.fabric.langchain.deepagents"),
            ("hermes", "nvidia.fabric.hermes"),
        ],
    )
    def test_supported_harness_kinds_translate_to_adapter_ids(
        self,
        kind: str,
        adapter_id: str,
    ) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "selected"
        payload["harnesses"] = {"selected": {"kind": kind}}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.harness.adapter_id == adapter_id

    def test_unknown_selected_harness_rejected(self) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        with pytest.raises(FabricTranslationError, match="Unknown configured harness 'claude'"):
            translate_agent_config(config, harness_name="claude")

    def test_unsupported_harness_kind_rejected(self) -> None:
        payload = _example_yaml_config()
        payload["harnesses"]["custom"] = {"kind": "custom"}
        payload["default_harness"] = "custom"
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="Unsupported harness kind 'custom'"):
            translate_agent_config(config)

    def test_missing_model_rejected(self) -> None:
        payload = _example_yaml_config()
        payload["models"] = {}
        payload["default_harness"] = "codex"
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="no models.default is configured"):
            translate_agent_config(config)

    def test_relay_telemetry_uses_latest_fabric_shape(self) -> None:
        payload = copy.deepcopy(_example_yaml_config())
        payload["telemetry"]["enabled"] = True
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.telemetry.providers["relay"].config is None
        assert fabric_config.relay.project == "example-agent"
        assert fabric_config.relay.output_dir == "./artifacts/relay"
        assert fabric_config.relay.observability.model_dump(exclude_none=True) == {
            "version": 1,
            "atif": {
                "enabled": True,
                "filename_template": "trajectory-{session_id}.atif.json",
                "output_directory": "./artifacts/relay",
                "agent_name": "example-agent",
                "model_name": "nvidia/nemotron-3-nano-30b-a3b",
            },
            "atof": {
                "enabled": True,
                "filename": "events.atof.jsonl",
                "mode": "overwrite",
                "output_directory": "./artifacts/relay",
            },
        }

    def test_translates_quoted_stdio_command_and_arguments(self) -> None:
        payload = _example_yaml_config()
        payload["mcp"] = {
            "servers": {
                "calculator": {
                    "transport": "stdio",
                    "command": "/path with spaces/calculator",
                    "args": ["--label", "two words"],
                }
            }
        }

        fabric_config = translate_agent_config(AgentConfig.model_validate(payload))

        assert fabric_config.mcp.servers["calculator"].url == ("'/path with spaces/calculator' --label 'two words'")
