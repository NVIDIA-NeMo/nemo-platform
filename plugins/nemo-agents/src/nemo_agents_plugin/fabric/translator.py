# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Translate Platform-owned agent config into typed in-memory FabricConfig."""

from __future__ import annotations

import importlib
from typing import Any

from nemo_agents_plugin.agent_config import AgentConfig, HarnessConfig, ModelConfig

HARNESS_ADAPTER_IDS = {
    "claude": "nvidia.fabric.claude",
    "codex": "nvidia.fabric.codex.cli",
    "deepagents": "nvidia.fabric.langchain.deepagents",
    "hermes": "nvidia.fabric.hermes",
}


class FabricTranslationError(ValueError):
    """Raised when Platform agent config cannot be translated to Fabric config."""


def translate_agent_config(config: AgentConfig, harness_name: str | None = None) -> Any:
    """Translate Platform-owned agent config into a typed in-memory FabricConfig.

    The Fabric SDK import is intentionally local to this function so existing
    NAT-backed NeMo Agents paths do not require Fabric to be installed.
    """

    (
        FabricConfig,
        HarnessConfig_,
        MetadataConfig,
        ModelConfig_,
        EnvironmentConfig,
    ) = _fabric_model_types()

    selected_harness_name, harness = _select_harness(config, harness_name)
    model = _resolve_model(config, selected_harness_name, harness)

    fabric_config = FabricConfig(
        metadata=MetadataConfig(name=config.name, description=config.description or None),
        harness=HarnessConfig_(
            adapter_id=_adapter_id_for_harness(harness),
            resolution="preinstalled",
            settings=harness.settings,
        ),
        models={
            "default": ModelConfig_(**_model_payload(model)),
        },
        environment=EnvironmentConfig(
            provider=config.environment.provider,
            workspace=config.environment.workspace,
            artifacts=config.environment.artifacts,
            settings=config.environment.settings,
        ),
    )

    _apply_telemetry(fabric_config, config, model)
    return fabric_config


def _fabric_model_types() -> tuple[type, type, type, type, type]:
    # TODO(AIRCORE-896): Keep this import lazy until Fabric SDK/runtime wheels
    # are available to the repo resolver and can be added as plugin dependencies.
    try:
        nemo_fabric = importlib.import_module("nemo_fabric")
    except ImportError as error:
        raise FabricTranslationError(
            "NeMo Fabric SDK is required to translate nemo-agents-spec-v1 config to FabricConfig."
        ) from error

    return (
        getattr(nemo_fabric, "FabricConfig"),
        getattr(nemo_fabric, "HarnessConfig"),
        getattr(nemo_fabric, "MetadataConfig"),
        getattr(nemo_fabric, "ModelConfig"),
        getattr(nemo_fabric, "EnvironmentConfig"),
    )


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
