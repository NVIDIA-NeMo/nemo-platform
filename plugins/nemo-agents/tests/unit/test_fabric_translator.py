# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Platform agent config to FabricConfig translation."""

from __future__ import annotations

import copy
import importlib
import sys
import types
from typing import Any

import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.translator import FabricTranslationError, translate_agent_config


class _FabricObject:
    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeFabricConfig(_FabricObject):
    def enable_relay(
        self,
        *,
        project: str | None = None,
        output_dir: str | None = None,
        observability: dict[str, Any] | None = None,
    ) -> "_FakeFabricConfig":
        self.telemetry = _FabricObject(providers={"relay": {}})
        self.relay = _FabricObject(
            project=project,
            output_dir=output_dir,
            observability=observability,
        )
        return self


@pytest.fixture()
def fake_nemo_fabric(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("nemo_fabric")
    setattr(module, "EnvironmentConfig", _FabricObject)
    setattr(module, "FabricConfig", _FakeFabricConfig)
    setattr(module, "HarnessConfig", _FabricObject)
    setattr(module, "MetadataConfig", _FabricObject)
    setattr(module, "ModelConfig", _FabricObject)
    monkeypatch.setitem(sys.modules, "nemo_fabric", module)


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
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "system_prompt": "You are a concise assistant.",
                },
            },
            "codex": {
                "kind": "codex",
                "settings": {
                    "sandbox": "workspace-write",
                    "skip_git_repo_check": True,
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
    def test_translates_default_harness(self, fake_nemo_fabric: None) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        fabric_config = translate_agent_config(config)

        assert fabric_config.metadata.name == "example-agent"
        assert fabric_config.metadata.description == "Example Agent"
        assert fabric_config.harness.adapter_id == "nvidia.fabric.hermes"
        assert fabric_config.harness.resolution == "preinstalled"
        assert fabric_config.harness.settings["system_prompt"] == "You are a concise assistant."
        assert fabric_config.models["default"].provider == "nvidia"
        assert fabric_config.models["default"].model == "nvidia/nemotron-3-nano-30b-a3b"
        assert fabric_config.environment.provider == "local"
        assert fabric_config.environment.workspace == "./workspace"
        assert fabric_config.environment.artifacts == "./artifacts"
        assert not hasattr(fabric_config, "relay")

    def test_selected_harness_uses_default_model(self, fake_nemo_fabric: None) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        fabric_config = translate_agent_config(config, harness_name="codex")

        assert fabric_config.harness.adapter_id == "nvidia.fabric.codex.cli"
        assert fabric_config.harness.settings["sandbox"] == "workspace-write"
        assert fabric_config.models["default"].provider == "openai"
        assert fabric_config.models["default"].model == "openai/gpt-5.4"

    @pytest.mark.parametrize(
        ("kind", "adapter_id"),
        [
            ("claude", "nvidia.fabric.claude"),
            ("codex", "nvidia.fabric.codex.cli"),
            ("deepagents", "nvidia.fabric.langchain.deepagents"),
            ("hermes", "nvidia.fabric.hermes"),
        ],
    )
    def test_supported_harness_kinds_translate_to_adapter_ids(
        self,
        fake_nemo_fabric: None,
        kind: str,
        adapter_id: str,
    ) -> None:
        payload = _example_yaml_config()
        payload["default_harness"] = "selected"
        payload["harnesses"] = {"selected": {"kind": kind}}
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.harness.adapter_id == adapter_id

    def test_unknown_selected_harness_rejected(self, fake_nemo_fabric: None) -> None:
        config = AgentConfig.model_validate(_example_yaml_config())

        with pytest.raises(FabricTranslationError, match="Unknown configured harness 'claude'"):
            translate_agent_config(config, harness_name="claude")

    def test_unsupported_harness_kind_rejected(self, fake_nemo_fabric: None) -> None:
        payload = _example_yaml_config()
        payload["harnesses"]["custom"] = {"kind": "custom"}
        payload["default_harness"] = "custom"
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="Unsupported harness kind 'custom'"):
            translate_agent_config(config)

    def test_missing_model_rejected(self, fake_nemo_fabric: None) -> None:
        payload = _example_yaml_config()
        payload["models"] = {}
        payload["default_harness"] = "codex"
        config = AgentConfig.model_validate(payload)

        with pytest.raises(FabricTranslationError, match="no models.default is configured"):
            translate_agent_config(config)

    def test_relay_telemetry_uses_latest_fabric_shape(self, fake_nemo_fabric: None) -> None:
        payload = copy.deepcopy(_example_yaml_config())
        payload["telemetry"]["enabled"] = True
        config = AgentConfig.model_validate(payload)

        fabric_config = translate_agent_config(config)

        assert fabric_config.telemetry.providers == {"relay": {}}
        assert fabric_config.relay.project == "example-agent"
        assert fabric_config.relay.output_dir == "./artifacts/relay"
        assert fabric_config.relay.observability == {
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

    def test_missing_fabric_dependency_reports_actionable_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_import_module = importlib.import_module

        def fake_import_module(name: str, package: str | None = None) -> Any:
            if name == "nemo_fabric":
                raise ImportError("No module named 'nemo_fabric'")
            return real_import_module(name, package)

        monkeypatch.delitem(sys.modules, "nemo_fabric", raising=False)
        monkeypatch.setattr(importlib, "import_module", fake_import_module)
        config = AgentConfig.model_validate(_example_yaml_config())

        with pytest.raises(FabricTranslationError, match="NeMo Fabric SDK is required"):
            translate_agent_config(config)
