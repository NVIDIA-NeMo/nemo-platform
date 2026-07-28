# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Translate Platform-owned agent config into typed in-memory FabricConfig."""

from __future__ import annotations

from typing import Any

# CI type-checks this plugin via ty extra-paths without installing nemo-agents deps.
import nemo_fabric as fabric  # ty: ignore[unresolved-import]
from nemo_agents_plugin.agent_config import AgentConfig, HarnessConfig, ModelConfig, NatHarnessSettings
from pydantic import ValidationError

HARNESS_ADAPTER_IDS = {
    "claude": "nvidia.fabric.claude",
    "codex": "nvidia.fabric.codex",
    "deepagents": "nvidia.fabric.langchain.deepagents",
    "hermes": "nvidia.fabric.hermes",
    "nat": "nvidia.nemo.platform.nat",
}


class FabricTranslationError(ValueError):
    """Raised when Platform agent config cannot be translated to Fabric config."""


def translate_agent_config(config: AgentConfig, harness_name: str | None = None) -> fabric.FabricConfig:
    """Translate Platform-owned agent config into a typed in-memory FabricConfig."""
    selected_harness_name, harness = _select_harness(config, harness_name)
    _validate_untranslated_shared_fields(config)
    model: ModelConfig | None = None
    models: dict[str, fabric.ModelConfig | dict[str, Any]] = {}
    if harness.kind == "nat":
        nat_settings = _validate_nat_harness(config, selected_harness_name, harness)
        if nat_settings.workflow == "react":
            model = _resolve_model(config, selected_harness_name, harness)
            models["default"] = fabric.ModelConfig(**_model_payload(model))
    else:
        model = _resolve_model(config, selected_harness_name, harness)
        models["default"] = fabric.ModelConfig(**_model_payload(model))

    fabric_config = fabric.FabricConfig(
        metadata=fabric.MetadataConfig(name=config.name, description=config.description or None),
        harness=fabric.HarnessConfig(
            adapter_id=_adapter_id_for_harness(harness),
            resolution="preinstalled",
            settings=_harness_settings(harness),
        ),
        models=models,
        environment=fabric.EnvironmentConfig(
            provider=config.environment.provider,
            workspace=config.environment.workspace,
            artifacts=config.environment.artifacts,
            settings=config.environment.settings,
        ),
        skills=_skills_config(config),
        mcp=_mcp_config(config),
        tools=_tools_config(config),
    )

    if model is not None:
        _apply_telemetry(fabric_config, config, model)
    return fabric_config


def _select_harness(config: AgentConfig, harness_name: str | None) -> tuple[str, HarnessConfig]:
    selected_harness_name = harness_name or config.default_harness
    harness = config.harnesses.get(selected_harness_name)
    if harness is None:
        available = ", ".join(sorted(config.harnesses))
        raise FabricTranslationError(
            f"Unknown configured harness {selected_harness_name!r}. Configured harnesses: {available}"
        )
    return selected_harness_name, harness


def _adapter_id_for_harness(harness: HarnessConfig) -> str:
    adapter_id = HARNESS_ADAPTER_IDS.get(harness.kind)
    if adapter_id is None:
        available = ", ".join(sorted(HARNESS_ADAPTER_IDS))
        raise FabricTranslationError(f"Unsupported harness kind {harness.kind!r}. Supported harness kinds: {available}")
    return adapter_id


def _resolve_model(config: AgentConfig, harness_name: str, harness: HarnessConfig) -> ModelConfig:
    if harness.model is not None:
        return harness.model

    model = config.models.get("default")
    if model is None:
        raise FabricTranslationError(
            f"Harness {harness_name!r} does not define a model and no models.default is configured."
        )
    return model


def _validate_nat_harness(
    config: AgentConfig,
    harness_name: str,
    harness: HarnessConfig,
) -> NatHarnessSettings:
    try:
        settings = NatHarnessSettings.model_validate(harness.settings)
    except ValidationError as error:
        raise FabricTranslationError(f"NAT harness {harness_name!r} has invalid settings: {error}") from error

    if settings.workflow == "current_timezone" and harness.model is not None:
        raise FabricTranslationError(f"NAT harness {harness_name!r} current_timezone workflow does not accept a model.")
    if config.telemetry.enabled:
        raise FabricTranslationError(f"NAT harness {harness_name!r} does not map Platform telemetry.")
    return settings


def _harness_settings(harness: HarnessConfig) -> dict[str, Any]:
    return dict(harness.settings)


def _model_payload(model: ModelConfig) -> dict[str, Any]:
    return model.model_dump(exclude_none=True)


def _validate_untranslated_shared_fields(config: AgentConfig) -> None:
    if config.prompts:
        raise FabricTranslationError(
            "Top-level prompts are not translated yet. Configure prompt settings under the selected harness instead."
        )


def _skills_config(config: AgentConfig) -> fabric.SkillConfig | None:
    if config.skills is None:
        return None
    return fabric.SkillConfig.model_validate({"paths": config.skills.paths})


def _mcp_config(config: AgentConfig) -> fabric.McpConfig | None:
    if config.mcp is None:
        return None
    return fabric.McpConfig(
        servers={name: fabric.McpServerConfig(**server.model_dump()) for name, server in config.mcp.servers.items()}
    )


def _tools_config(config: AgentConfig) -> fabric.ToolsConfig | None:
    if config.tools is None:
        return None
    return fabric.ToolsConfig(blocked=config.tools.blocked)


def _apply_telemetry(fabric_config: Any, config: AgentConfig, model: ModelConfig) -> None:
    telemetry = config.telemetry
    if not telemetry.enabled:
        return

    provider = telemetry.provider or "relay"
    if provider != "relay":
        raise FabricTranslationError(f"Unsupported telemetry provider {provider!r}. Only 'relay' is supported.")

    fabric_config.enable_relay(
        project=telemetry.project,
        output_dir=telemetry.output_dir,
        observability=_relay_observability_config(config, model),
    )


def _relay_observability_config(config: AgentConfig, model: ModelConfig) -> dict[str, Any]:
    telemetry = config.telemetry
    observability: dict[str, Any] = {"version": 1}

    if telemetry.atif is not None:
        atif = dict(telemetry.atif)
        if telemetry.output_dir is not None:
            atif.setdefault("output_directory", telemetry.output_dir)
        atif.setdefault("agent_name", config.name)
        atif.setdefault("model_name", model.model)
        observability["atif"] = atif

    if telemetry.atof is not None:
        atof = dict(telemetry.atof)
        if telemetry.output_dir is not None:
            atof.setdefault("output_directory", telemetry.output_dir)
        observability["atof"] = atof

    return observability
