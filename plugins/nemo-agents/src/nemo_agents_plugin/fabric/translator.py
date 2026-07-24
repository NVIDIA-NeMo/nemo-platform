# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Translate Platform-owned agent config into typed in-memory FabricConfig."""

from __future__ import annotations

import shlex
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
        mcp=_translate_mcp(config),
    )

    _apply_telemetry(fabric_config, config, model)
    return fabric_config


def _translate_mcp(config: AgentConfig) -> fabric.McpConfig | None:
    if not config.mcp.servers:
        return None

    servers: dict[str, fabric.McpServerConfig] = {}
    for name, server in config.mcp.servers.items():
        if server.transport == "stdio":
            assert server.command is not None
            target = shlex.join([server.command, *server.args])
        else:
            assert server.url is not None
            target = server.url
        servers[name] = fabric.McpServerConfig(
            transport=server.transport,
            url=target,
            exposure=server.exposure,
        )
    return fabric.McpConfig(servers=servers)


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
