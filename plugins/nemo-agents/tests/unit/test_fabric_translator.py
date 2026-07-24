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
    def test_repository_example_configures_codex_hermes_and_nat_adapters(self) -> None:
        example_path = Path(__file__).parents[2] / "examples/nemo-agent-config/agent.yaml"
        config = load_agent_config(example_path)

        codex_config = translate_agent_config(config)
        hermes_config = translate_agent_config(config.model_copy(update={"default_harness": "hermes"}))
        nat_config = translate_agent_config(config.model_copy(update={"default_harness": "nat"}))

        assert codex_config.harness.adapter_id == "nvidia.fabric.codex"
        assert "skip_git_repo_check" not in codex_config.harness.settings
        assert hermes_config.harness.adapter_id == "nvidia.fabric.hermes"
        assert hermes_config.harness.settings["python_env"] == "HERMES_ADAPTER_PYTHON"
        assert nat_config.harness.adapter_id == "nvidia.nemo.platform.nat"
        assert nat_config.models["default"].provider == "nvidia"
        assert nat_config.models["default"].model == "nvidia/nemotron-3-nano-30b-a3b"
        assert nat_config.harness.settings == {
            "workflow": "react",
            "tools": ["calculator", "current_datetime"],
        }

    @pytest.mark.parametrize("example_name", ["nat-calculator", "nat-email-phishing"])
    def test_repository_nat_examples_are_self_contained_agent_configs(self, example_name: str) -> None:
        example_dir = Path(__file__).parents[2] / "examples/nemo-agent-config" / example_name
        config = load_agent_config(example_dir / "agent.yaml")

        fabric_config = translate_agent_config(config)

        assert fabric_config.harness.adapter_id == "nvidia.nemo.platform.nat"
        assert fabric_config.harness.settings["workflow"] == "react"
        assert "config_file" not in fabric_config.harness.settings
        assert "llm_map" not in fabric_config.harness.settings
        assert not (example_dir / "workflow.yml").exists()
        assert set(fabric_config.models) == {"default"}

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

    def test_translates_shared_capability_sections(self) -> None:
        payload = copy.deepcopy(_example_yaml_config())
        payload["skills"] = {"paths": ["skills/review"]}
        payload["mcp"] = {
            "servers": {
                "repo": {
                    "transport": "stdio",
                    "url": "repo-mcp --root .",
                    "exposure": "fabric_managed",
                }
            }
        }
        payload["tools"] = {"blocked": ["shell", "browser"]}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.skills.paths == ["skills/review"]
        assert fabric_config.mcp.servers["repo"].transport == "stdio"
        assert fabric_config.mcp.servers["repo"].url == "repo-mcp --root ."
        assert fabric_config.mcp.servers["repo"].exposure == "fabric_managed"
        assert fabric_config.tools.blocked == ["shell", "browser"]

    def test_top_level_prompts_rejected_until_shared_prompt_contract_exists(self) -> None:
        payload = copy.deepcopy(_example_yaml_config())
        payload["prompts"] = {"system": "prompts/system.md"}
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="Top-level prompts are not translated yet"):
            translate_agent_config(config)

    @pytest.mark.parametrize(
        ("kind", "adapter_id"),
        [
            ("claude", "nvidia.fabric.claude"),
            ("codex", "nvidia.fabric.codex"),
            ("deepagents", "nvidia.fabric.langchain.deepagents"),
            ("hermes", "nvidia.fabric.hermes"),
            ("nat", "nvidia.nemo.platform.nat"),
        ],
    )
    def test_supported_harness_kinds_translate_to_adapter_ids(
        self,
        kind: str,
        adapter_id: str,
    ) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "selected"
        payload["harnesses"] = {
            "selected": {
                "kind": kind,
                "settings": {"workflow": "current_timezone"} if kind == "nat" else {},
            }
        }
        if kind == "nat":
            payload["models"] = {}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.harness.adapter_id == adapter_id

    def test_nat_current_timezone_does_not_require_model(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "settings": {"workflow": "current_timezone"},
            }
        }
        payload["models"] = {}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.harness.adapter_id == "nvidia.nemo.platform.nat"
        assert fabric_config.harness.settings == {"workflow": "current_timezone"}
        assert fabric_config.models == {}
        assert fabric_config.telemetry is None
        assert fabric_config.relay is None

    def test_nat_current_timezone_rejects_inline_model(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "model": {
                    "provider": "nvidia",
                    "model": "unused",
                },
                "settings": {"workflow": "current_timezone"},
            }
        }
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="does not accept a model"):
            translate_agent_config(config)

    def test_nat_harness_requires_supported_workflow(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {"nat": {"kind": "nat"}}
        payload["models"] = {}
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="invalid settings"):
            translate_agent_config(config)

    def test_nat_react_harness_uses_inline_platform_model(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "model": {
                    "provider": "nvidia",
                    "model": "nvidia/example-model",
                },
                "settings": {
                    "workflow": "react",
                    "tools": ["calculator"],
                },
            }
        }
        payload["models"] = {}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.models["default"].provider == "nvidia"
        assert fabric_config.models["default"].model == "nvidia/example-model"

    def test_nat_react_harness_uses_top_level_default_model(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "settings": {
                    "workflow": "react",
                    "tools": ["calculator", "current_datetime"],
                },
            }
        }
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert set(fabric_config.models) == {"default"}
        assert fabric_config.models["default"].provider == "openai"
        assert fabric_config.models["default"].model == "openai/gpt-5.4"

    def test_nat_react_harness_requires_platform_model(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "settings": {
                    "workflow": "react",
                    "tools": ["calculator"],
                },
            }
        }
        payload["models"] = {}
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="no models.default is configured"):
            translate_agent_config(config)

    @pytest.mark.parametrize(
        "settings",
        [
            {"config_file": "./workflow.yml"},
            {"workflow": "react", "llm_map": {"llm": "default"}},
            {"workflow": "native_workflow"},
            {"workflow": "react", "tools": ["unknown"]},
            {"workflow": "react", "tools": ["calculator", "calculator"]},
        ],
    )
    def test_nat_harness_rejects_native_or_invalid_settings(self, settings: dict[str, Any]) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "settings": settings,
            }
        }
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="invalid settings"):
            translate_agent_config(config)

    def test_nat_harness_translates_shared_capabilities(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "settings": {
                    "workflow": "react",
                    "tools": ["calculator"],
                },
            }
        }
        payload["skills"] = {"paths": ["./skills/example"]}
        payload["mcp"] = {
            "servers": {
                "repo": {
                    "transport": "streamable-http",
                    "url": "http://localhost:9901/mcp",
                }
            }
        }
        payload["tools"] = {"blocked": ["calculator__divide"]}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert set(fabric_config.models) == {"default"}
        assert fabric_config.skills.paths == ["./skills/example"]
        assert fabric_config.mcp.servers["repo"].url == "http://localhost:9901/mcp"
        assert fabric_config.tools.blocked == ["calculator__divide"]

    def test_nat_harness_rejects_platform_telemetry(self) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "nat"
        payload["harnesses"] = {
            "nat": {
                "kind": "nat",
                "settings": {"workflow": "current_timezone"},
            }
        }
        payload["models"] = {}
        payload["telemetry"]["enabled"] = True
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="does not map Platform telemetry"):
            translate_agent_config(config)

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
