# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve an AgentEnvironment and merge its EnvironmentSpec into agent config.

An AgentDeployment references an :class:`AgentEnvironment` (by name or inline).
At create time the deployment route:

1. resolves the environment - dereferencing any ``"workspace/name"`` refs for
   the environment and its two specs into concrete inline specs;
2. merges the resolved EnvironmentSpec into the Platform-owned agent config
   (``nemo-agents-spec-v1``) so the Fabric translator sees a single config; and
3. snapshots the resolved ComputeSpec onto the deployment for the container
   backend.

Merge precedence is **Agent config wins over EnvironmentSpec**: the
EnvironmentSpec is the fulfillment/base layer, and any value the Agent set
explicitly is preserved. This keeps existing agent configs (authored without an
environment) behaving identically.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from nemo_agents_plugin.entities import (
    NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    AgentComputeSpec,
    AgentEnvironment,
    AgentEnvironmentInline,
    AgentEnvironmentSpec,
    ComputeSpecInline,
    EnvironmentSpecInline,
)
from nemo_platform_plugin.entities.base import parse_qualified_name
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError


class EnvironmentResolutionError(ValueError):
    """Raised when an AgentEnvironment or one of its specs cannot be resolved."""


@dataclass(frozen=True)
class ResolvedEnvironment:
    """Concrete environment/compute specs resolved from an AgentEnvironment."""

    environment_spec: EnvironmentSpecInline | None = None
    compute_spec: ComputeSpecInline | None = None


async def resolve_environment(
    environment: str | AgentEnvironmentInline | None,
    *,
    workspace: str,
    entity_client: NemoEntitiesClient,
) -> ResolvedEnvironment:
    """Resolve an AgentEnvironment (ref | inline | None) into concrete specs.

    Dereferences the environment and its ``environment_spec`` / ``compute_spec``
    refs. Missing refs raise :class:`EnvironmentResolutionError`. ``None`` yields
    an empty :class:`ResolvedEnvironment` (no environment configured).
    """
    if environment is None:
        return ResolvedEnvironment()

    resolved_env = await _resolve_agent_environment(environment, workspace=workspace, entity_client=entity_client)
    environment_spec = await _resolve_environment_spec(
        resolved_env.environment_spec, workspace=workspace, entity_client=entity_client
    )
    compute_spec = await _resolve_compute_spec(
        resolved_env.compute_spec, workspace=workspace, entity_client=entity_client
    )
    return ResolvedEnvironment(environment_spec=environment_spec, compute_spec=compute_spec)


async def _resolve_agent_environment(
    environment: str | AgentEnvironmentInline,
    *,
    workspace: str,
    entity_client: NemoEntitiesClient,
) -> AgentEnvironmentInline:
    if isinstance(environment, str):
        ref_workspace, name = parse_qualified_name(environment, default_workspace=workspace)
        try:
            return await entity_client.get(AgentEnvironment, name=name, workspace=ref_workspace)
        except NemoEntityNotFoundError as exc:
            raise EnvironmentResolutionError(
                f"AgentEnvironment '{name}' not found in workspace '{ref_workspace}'."
            ) from exc
    return environment


async def _resolve_environment_spec(
    spec: str | EnvironmentSpecInline | None,
    *,
    workspace: str,
    entity_client: NemoEntitiesClient,
) -> EnvironmentSpecInline | None:
    if spec is None:
        return None
    if isinstance(spec, str):
        ref_workspace, name = parse_qualified_name(spec, default_workspace=workspace)
        try:
            return await entity_client.get(AgentEnvironmentSpec, name=name, workspace=ref_workspace)
        except NemoEntityNotFoundError as exc:
            raise EnvironmentResolutionError(
                f"AgentEnvironmentSpec '{name}' not found in workspace '{ref_workspace}'."
            ) from exc
    return spec


async def _resolve_compute_spec(
    spec: str | ComputeSpecInline | None,
    *,
    workspace: str,
    entity_client: NemoEntitiesClient,
) -> ComputeSpecInline | None:
    if spec is None:
        return None
    if isinstance(spec, str):
        ref_workspace, name = parse_qualified_name(spec, default_workspace=workspace)
        try:
            return await entity_client.get(AgentComputeSpec, name=name, workspace=ref_workspace)
        except NemoEntityNotFoundError as exc:
            raise EnvironmentResolutionError(
                f"AgentComputeSpec '{name}' not found in workspace '{ref_workspace}'."
            ) from exc
    return spec


def merge_environment_spec_into_agent_config(
    config: dict[str, Any],
    env_spec: EnvironmentSpecInline | None,
) -> dict[str, Any]:
    """Merge a resolved EnvironmentSpec into a ``nemo-agents-spec-v1`` config.

    Returns a deep-copied config with the spec merged in. Merge precedence is
    Agent-config-wins: the Agent's explicitly-set values are preserved and the
    EnvironmentSpec only fills gaps or contributes additive keys.

    Only ``nemo-agents-spec-v1`` (Fabric) configs are merged; other formats are
    returned unchanged (they have no environment concept to fulfill).
    """
    if env_spec is None:
        return config
    if config.get("config_format") != NEMO_AGENTS_SPEC_CONFIG_FORMAT:
        return config

    merged = copy.deepcopy(config)
    _merge_environment_block(merged, env_spec)
    _merge_process_env(merged, env_spec)
    _merge_model_provider_override(merged, env_spec)
    _merge_mcp(merged, env_spec)
    return merged


def _merge_environment_block(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Fill FabricConfig.environment mirror fields where the Agent left them unset."""
    environment = config.setdefault("environment", {})
    if not isinstance(environment, dict):
        return

    # Scalar mirror fields: only fill when the Agent did not set them. The spec's
    # ``workspace_path`` maps onto the config's ``workspace`` (the harness path);
    # the entity/tenant ``workspace`` is unrelated and never merged here.
    scalar_fields = {
        "provider": "provider",
        "workspace_path": "workspace",
        "artifacts": "artifacts",
        "control_location": "control_location",
        "ownership": "ownership",
    }
    for spec_attr, config_key in scalar_fields.items():
        value = getattr(env_spec, spec_attr)
        if value is not None and config_key not in environment:
            environment[config_key] = value

    # Dict mirror fields: EnvironmentSpec is the base, Agent keys win on collision.
    for field in ("connection", "metadata", "settings"):
        spec_value = getattr(env_spec, field)
        if spec_value:
            environment[field] = {**spec_value, **environment.get(field, {})}


def _merge_process_env(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Merge plaintext env vars into environment.env (Agent keys win)."""
    if not env_spec.env:
        return
    environment = config.setdefault("environment", {})
    if not isinstance(environment, dict):
        return
    existing = environment.get("env")
    existing = existing if isinstance(existing, dict) else {}
    environment["env"] = {**env_spec.env, **existing}


def _merge_model_provider_override(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Apply an external model-provider override to models.default where unset."""
    override = env_spec.model_provider_override
    if override is None:
        return
    models = config.setdefault("models", {})
    if not isinstance(models, dict):
        return
    model = models.setdefault("default", {})
    if not isinstance(model, dict):
        return
    if "base_url" not in model:
        model["base_url"] = override.base_url
    if override.provider is not None and "provider" not in model:
        model["provider"] = override.provider
    if override.api_key is not None and "api_key_env" not in model:
        model["api_key_env"] = override.api_key


def _merge_mcp(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Fulfill Agent-declared MCP servers by name (Agent keys win)."""
    if not env_spec.mcp:
        return
    mcp = config.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        return
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        return

    for name, fulfillment in env_spec.mcp.items():
        server = servers.get(name)
        server = server if isinstance(server, dict) else {}
        # url: fill only when the Agent did not provide one.
        if "url" not in server:
            server["url"] = fulfillment.url
        # env + secrets merge into the server env; Agent-authored env wins.
        merged_env = {**fulfillment.env, **fulfillment.secrets}
        if merged_env:
            existing_env = server.get("env")
            existing_env = existing_env if isinstance(existing_env, dict) else {}
            server["env"] = {**merged_env, **existing_env}
        servers[name] = server
