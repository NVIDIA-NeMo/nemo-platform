# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Translate Platform-owned agent config into typed in-memory FabricConfig."""

from __future__ import annotations

from typing import Any

# CI type-checks this plugin via ty extra-paths without installing nemo-agents deps.
import nemo_fabric as fabric  # ty: ignore[unresolved-import]
from nemo_agents_plugin.agent_config import AgentConfig, HarnessConfig, ModelConfig

HARNESS_ADAPTER_IDS = {
    "claude": "nvidia.fabric.claude",
    "codex": "nvidia.fabric.codex",
    "deepagents": "nvidia.fabric.langchain.deepagents",
    "hermes": "nvidia.fabric.hermes",
}


class FabricTranslationError(ValueError):
    """Raised when Platform agent config cannot be translated to Fabric config."""


def translate_agent_config(config: AgentConfig, harness_name: str | None = None) -> fabric.FabricConfig:
    """Translate Platform-owned agent config into a typed in-memory FabricConfig."""
    selected_harness_name, harness = _select_harness(config, harness_name)
    model = _resolve_model(config, selected_harness_name, harness)
    _validate_untranslated_shared_fields(config)

    fabric_config = fabric.FabricConfig(
        metadata=fabric.MetadataConfig(name=config.name, description=config.description or None),
        harness=fabric.HarnessConfig(
            adapter_id=_adapter_id_for_harness(harness),
            resolution="preinstalled",
            settings=harness.settings,
        ),
        models={
            "default": fabric.ModelConfig(**_model_payload(model)),
        },
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


def _model_payload(model: ModelConfig) -> dict[str, Any]:
    return model.model_dump(exclude_none=True)


def _validate_untranslated_shared_fields(config: AgentConfig) -> None:
    if config.prompts:
        raise FabricTranslationError(
            "Top-level prompts are not translated yet. Configure prompt settings under the selected harness instead."
        )


def _skills_config(config: AgentConfig) -> Any:
    if config.skills is None:
        return None
    return fabric.SkillConfig(paths=config.skills.paths)


def _mcp_config(config: AgentConfig) -> Any:
    if config.mcp is None:
        return None
    return fabric.McpConfig(
        servers={name: fabric.McpServerConfig(**server.model_dump()) for name, server in config.mcp.servers.items()}
    )


def _tools_config(config: AgentConfig) -> Any:
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
    observability: dict[str, Any] = {"version": 2}

    if telemetry.atif is not None:
        atif = dict(telemetry.atif)
        if telemetry.output_dir is not None:
            atif.setdefault("output_directory", telemetry.output_dir)
        atif.setdefault("agent_name", config.name)
        atif.setdefault("model_name", model.model)
        observability["atif"] = atif

    if telemetry.atof is not None:
        observability["atof"] = _relay_atof_config(telemetry.atof, output_dir=telemetry.output_dir)

    return observability


def _relay_atof_config(atof_config: dict[str, Any], output_dir: str | None) -> dict[str, Any]:
    atof = dict(atof_config)
    sinks = list(atof.pop("sinks", []) or [])

    file_sink = {"type": "file"}
    if output_dir is not None:
        file_sink["output_directory"] = output_dir
    for key in ("output_directory", "filename", "mode"):
        if key in atof:
            file_sink[key] = atof.pop(key)
    if len(file_sink) > 1:
        sinks.insert(0, file_sink)

    for endpoint in atof.pop("endpoints", []) or []:
        stream_sink = dict(endpoint)
        endpoint_url = stream_sink.pop("endpoint", None)
        if endpoint_url is not None and "url" not in stream_sink:
            stream_sink["url"] = endpoint_url
        stream_sink["type"] = "stream"
        sinks.append(stream_sink)

    translated = {"enabled": atof.pop("enabled", False)}
    if sinks:
        translated["sinks"] = sinks
    translated.update(atof)
    return translated
