# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Platform-owned agent.yaml config models."""

from __future__ import annotations

import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from pydantic import ValidationError


def _example_yaml_config() -> dict:
    return {
        "name": "fabric-mvp-spike",
        "description": "Fabric MVP Spike",
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
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "max_iterations": 1,
                    "max_tokens": 512,
                    "reasoning_config": {"effort": "none"},
                    "enabled_toolsets": [],
                    "system_prompt": "You are a concise smoke test assistant.",
                },
            },
            "codex": {
                "kind": "codex",
                "settings": {
                    "sandbox": "workspace-write",
                    "skip_git_repo_check": True,
                    "config_overrides": {"model_reasoning_effort": "high"},
                },
            },
        },
        "models": {
            "default": {
                "provider": "openai",
                "model": "openai/gpt-5.4",
            },
        },
        "prompts": {
            "system": "prompts/system.md",
        },
        "skills": None,
        "environment": {
            "workspace": "./workspace",
            "artifacts": "./artifacts",
        },
        "telemetry": {
            "enabled": False,
            "provider": "relay",
            "output_dir": "./artifacts/relay",
            "project": "fabric-mvp-spike",
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


class TestAgentConfig:
    def test_example_yaml_config_validates(self) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        assert config.name == "fabric-mvp-spike"
        assert config.default_harness == "hermes"
        assert config.harnesses["hermes"].model is not None
        assert config.harnesses["hermes"].model.provider == "nvidia"
        assert config.harnesses["codex"].settings["sandbox"] == "workspace-write"
        assert config.models["default"].model == "openai/gpt-5.4"
        assert config.skills is None
        assert config.telemetry.atif == {
            "enabled": True,
            "filename_template": "trajectory-{session_id}.atif.json",
        }

    def test_defaults_fill_optional_sections(self) -> None:
        config = AgentConfig.model_validate(
            {
                "name": "minimal-agent",
                "default_harness": "codex",
                "harnesses": {"codex": {"kind": "codex"}},
            }
        )

        assert config.description == ""
        assert config.models == {}
        assert config.prompts == {}
        assert config.environment.provider == "local"
        assert config.environment.workspace == "./workspace"
        assert config.environment.artifacts == "./artifacts"
        assert config.telemetry.enabled is False

    def test_default_harness_must_reference_configured_harness(self) -> None:
        with pytest.raises(ValidationError, match="default_harness must reference one of harnesses: codex"):
            AgentConfig.model_validate(
                {
                    "name": "bad-agent",
                    "default_harness": "hermes",
                    "harnesses": {"codex": {"kind": "codex"}},
                }
            )

    def test_unknown_top_level_fields_rejected(self) -> None:
        payload = _example_yaml_config()
        payload["unexpected"] = "value"

        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            AgentConfig.model_validate(payload)

    def test_unknown_nested_fields_rejected_outside_settings(self) -> None:
        payload = _example_yaml_config()
        payload["harnesses"]["codex"]["unknown"] = "value"

        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            AgentConfig.model_validate(payload)
