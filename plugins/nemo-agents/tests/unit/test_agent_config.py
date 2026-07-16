# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Platform-owned agent.yaml config models."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from nemo_agents_plugin.agent_config import (
    AgentConfig,
    AgentConfigLoadError,
    load_agent_config,
    load_agent_config_from_dir,
)
from pydantic import ValidationError


def _example_yaml_config() -> dict:
    return {
        "config_format": "nemo-agents-spec-v1",
        "name": "test-agent",
        "description": "Test agent config",
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
            "project": "test-agent",
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

        assert config.config_format == "nemo-agents-spec-v1"
        assert config.name == "test-agent"
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
                "config_format": "nemo-agents-spec-v1",
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
                    "config_format": "nemo-agents-spec-v1",
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

    def test_config_format_must_match_platform_spec_version(self) -> None:
        payload = _example_yaml_config()
        payload["config_format"] = "nat-workflow-v1"

        with pytest.raises(ValidationError, match="Input should be 'nemo-agents-spec-v1'"):
            AgentConfig.model_validate(payload)

    def test_unknown_nested_fields_rejected_outside_settings(self) -> None:
        payload = _example_yaml_config()
        payload["harnesses"]["codex"]["unknown"] = "value"

        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            AgentConfig.model_validate(payload)


def _write_agent_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


class TestLoadAgentConfig:
    def test_load_agent_config_reads_yaml_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "custom-agent.yaml"
        _write_agent_yaml(config_path, _example_yaml_config())

        config = load_agent_config(config_path)

        assert config.name == "test-agent"
        assert config.default_harness == "hermes"

    def test_load_agent_config_from_dir_uses_canonical_filename(self, tmp_path: Path) -> None:
        config_path = tmp_path / "agent.yaml"
        _write_agent_yaml(config_path, _example_yaml_config())

        config = load_agent_config_from_dir(tmp_path)

        assert config.name == "test-agent"

    def test_missing_file_reports_load_error(self, tmp_path: Path) -> None:
        with pytest.raises(AgentConfigLoadError, match="Unable to read agent config"):
            load_agent_config(tmp_path / "missing.yaml")

    def test_invalid_yaml_reports_load_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "agent.yaml"
        config_path.write_text("name: [", encoding="utf-8")

        with pytest.raises(AgentConfigLoadError, match="YAML parse error"):
            load_agent_config(config_path)

    def test_non_mapping_yaml_reports_load_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "agent.yaml"
        config_path.write_text("- not-a-mapping\n", encoding="utf-8")

        with pytest.raises(AgentConfigLoadError, match="root must be a YAML mapping"):
            load_agent_config(config_path)

    def test_validation_error_reports_load_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "agent.yaml"
        payload = _example_yaml_config()
        del payload["default_harness"]
        _write_agent_yaml(config_path, payload)

        with pytest.raises(AgentConfigLoadError, match="Invalid agent config"):
            load_agent_config(config_path)
