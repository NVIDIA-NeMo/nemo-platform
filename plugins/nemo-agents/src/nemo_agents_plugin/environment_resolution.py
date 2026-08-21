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

Merge precedence is **EnvironmentSpec wins over the Agent config**: the Agent
config supplies defaults, and the EnvironmentSpec overrides them where it sets a
value. Fields the EnvironmentSpec leaves unset fall back to the Agent's
defaults, so an agent authored without an environment behaves identically.

This ordering is the middle tier of an intended precedence chain
``deployment overrides > EnvironmentSpec > Agent defaults``. A future
deployment-specific override layer (e.g. an inline ``environment_overrides`` on
the deployment) slots in by applying this same merge a second time with the
higher-priority spec last, so each successive layer overrides the previous.
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
    """Override FabricConfig.environment mirror fields with the EnvironmentSpec's values."""
    environment = config.setdefault("environment", {})
    if not isinstance(environment, dict):
        return

    # Scalar mirror fields: the EnvironmentSpec overrides the Agent's value when
    # it sets one; an unset spec field leaves the Agent default in place. The
    # spec's ``workspace_path``/``artifacts_path`` map onto the config's
    # ``workspace``/``artifacts`` (the harness paths); the entity/tenant
    # ``workspace`` is unrelated and never merged here.
    scalar_fields = {
        "provider": "provider",
        "workspace_path": "workspace",
        "artifacts_path": "artifacts",
        "control_location": "control_location",
        "ownership": "ownership",
    }
    for spec_attr, config_key in scalar_fields.items():
        value = getattr(env_spec, spec_attr)
        if value is not None:
            environment[config_key] = value

    # Dict mirror fields: Agent supplies the base, EnvironmentSpec keys win on collision.
    for field in ("connection", "metadata", "settings"):
        spec_value = getattr(env_spec, field)
        if spec_value:
            environment[field] = {**environment.get(field, {}), **spec_value}


def _merge_process_env(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Merge plaintext env vars into environment.env (EnvironmentSpec keys win)."""
    if not env_spec.env:
        return
    environment = config.setdefault("environment", {})
    if not isinstance(environment, dict):
        return
    existing = environment.get("env")
    existing = existing if isinstance(existing, dict) else {}
    environment["env"] = {**existing, **env_spec.env}


def _merge_model_provider_override(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Apply an external model-provider override to models.default (overrides the Agent)."""
    override = env_spec.model_provider_override
    if override is None:
        return
    models = config.setdefault("models", {})
    if not isinstance(models, dict):
        return
    model = models.setdefault("default", {})
    if not isinstance(model, dict):
        return
    model["base_url"] = override.base_url
    if override.provider is not None:
        model["provider"] = override.provider
    if override.api_key is not None:
        model["api_key_env"] = override.api_key


def _merge_mcp(config: dict[str, Any], env_spec: EnvironmentSpecInline) -> None:
    """Fulfill Agent-declared MCP servers by name (EnvironmentSpec fulfillment wins).

    McpFulfillment is a request/fulfill contract: the Agent DECLARES an MCP
    server by name and the EnvironmentSpec PROVIDES its url/env/secrets. A
    fulfillment whose name the Agent did not declare is ignored - an environment
    must not add MCP servers the Agent never requested. For a declared server the
    fulfillment overrides the Agent's url and env on collision.
    """
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
        # Only fulfill servers the Agent declared; skip undeclared names.
        if not isinstance(server, dict):
            continue
        # url: the fulfillment's endpoint overrides the Agent's.
        server["url"] = fulfillment.url
        # env + secrets merge into the server env; fulfillment values win on collision.
        merged_env = {**fulfillment.env, **fulfillment.secrets}
        if merged_env:
            existing_env = server.get("env")
            existing_env = existing_env if isinstance(existing_env, dict) else {}
            server["env"] = {**existing_env, **merged_env}
        servers[name] = server
