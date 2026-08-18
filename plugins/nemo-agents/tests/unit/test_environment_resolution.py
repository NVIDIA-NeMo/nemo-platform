# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for AgentEnvironment resolution and config merge."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from nemo_agents_plugin.entities import (
    NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    AgentComputeSpec,
    AgentEnvironment,
    AgentEnvironmentInline,
    AgentEnvironmentSpec,
    ComputeSpecInline,
    EnvironmentSpecInline,
    McpFulfillment,
    ModelProviderOverride,
)
from nemo_agents_plugin.environment_resolution import (
    EnvironmentResolutionError,
    merge_environment_spec_into_agent_config,
    resolve_environment,
)
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError


def _agent_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "config_format": NEMO_AGENTS_SPEC_CONFIG_FORMAT,
        "name": "fabric-agent",
        "default_harness": "hermes",
        "harnesses": {"hermes": {"kind": "hermes"}},
        "models": {"default": {"provider": "openai", "model": "openai/gpt-5.4"}},
        "environment": {"provider": "local"},
    }
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# resolve_environment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_none_returns_empty() -> None:
    resolved = await resolve_environment(None, workspace="default", entity_client=AsyncMock())
    assert resolved.environment_spec is None
    assert resolved.compute_spec is None


@pytest.mark.asyncio
async def test_resolve_inline_environment_with_inline_specs() -> None:
    environment = AgentEnvironmentInline(
        environment_spec=EnvironmentSpecInline(env={"FOO": "bar"}),
        compute_spec=ComputeSpecInline(resources={"limits": {"cpu": "2"}}),
    )
    resolved = await resolve_environment(environment, workspace="default", entity_client=AsyncMock())
    assert resolved.environment_spec is not None
    assert resolved.environment_spec.env == {"FOO": "bar"}
    assert resolved.compute_spec is not None
    assert resolved.compute_spec.resources.limits == {"cpu": "2"}


@pytest.mark.asyncio
async def test_resolve_environment_ref_dereferences_all_entities() -> None:
    env_entity = AgentEnvironment(
        name="env1",
        workspace="default",
        environment_spec="default/espec",
        compute_spec="default/cspec",
    )
    espec = AgentEnvironmentSpec(name="espec", workspace="default", env={"A": "1"})
    cspec = AgentComputeSpec(name="cspec", workspace="default", resources={"requests": {"cpu": "1"}})

    entity_client = AsyncMock()
    entity_client.get = AsyncMock(side_effect=[env_entity, espec, cspec])

    resolved = await resolve_environment("default/env1", workspace="default", entity_client=entity_client)

    assert resolved.environment_spec is not None
    assert resolved.environment_spec.env == {"A": "1"}
    assert resolved.compute_spec is not None
    assert resolved.compute_spec.resources.requests == {"cpu": "1"}
    # AgentEnvironment, then its two specs.
    assert entity_client.get.await_count == 3


@pytest.mark.asyncio
async def test_resolve_missing_environment_ref_raises() -> None:
    entity_client = AsyncMock()
    entity_client.get = AsyncMock(side_effect=NemoEntityNotFoundError("gone"))
    with pytest.raises(EnvironmentResolutionError, match="AgentEnvironment 'env1' not found"):
        await resolve_environment("default/env1", workspace="default", entity_client=entity_client)


@pytest.mark.asyncio
async def test_resolve_missing_spec_ref_raises() -> None:
    env_entity = AgentEnvironment(name="env1", workspace="default", environment_spec="default/missing")
    entity_client = AsyncMock()
    entity_client.get = AsyncMock(side_effect=[env_entity, NemoEntityNotFoundError("gone")])
    with pytest.raises(EnvironmentResolutionError, match="AgentEnvironmentSpec 'missing' not found"):
        await resolve_environment("default/env1", workspace="default", entity_client=entity_client)


# ---------------------------------------------------------------------------
# merge_environment_spec_into_agent_config
# ---------------------------------------------------------------------------


def test_merge_none_spec_returns_config_unchanged() -> None:
    config = _agent_config()
    assert merge_environment_spec_into_agent_config(config, None) is config


def test_merge_ignores_non_fabric_config() -> None:
    config = {"config_format": "nat-workflow-v1", "functions": {}}
    spec = EnvironmentSpecInline(env={"FOO": "bar"})
    assert merge_environment_spec_into_agent_config(config, spec) is config


def test_merge_env_agent_wins_on_collision() -> None:
    config = _agent_config(environment={"provider": "local", "env": {"SHARED": "agent"}})
    spec = EnvironmentSpecInline(env={"SHARED": "spec", "ONLY_SPEC": "spec"})
    merged = merge_environment_spec_into_agent_config(config, spec)
    assert merged["environment"]["env"] == {"SHARED": "agent", "ONLY_SPEC": "spec"}
    # Original is not mutated (deep copy).
    assert config["environment"]["env"] == {"SHARED": "agent"}


def test_merge_environment_mirror_fields_fill_only_when_unset() -> None:
    config = _agent_config(environment={"provider": "docker"})
    spec = EnvironmentSpecInline(
        provider="k8s",
        workspace_path="/ws",
        artifacts="/artifacts",
        control_location="in_env_control",
        ownership="fabric_owned",
        connection={"url": "http://x"},
    )
    merged = merge_environment_spec_into_agent_config(config, spec)
    env = merged["environment"]
    # Agent explicitly set provider -> preserved.
    assert env["provider"] == "docker"
    # Agent left these unset -> filled from spec (workspace_path -> workspace).
    assert env["workspace"] == "/ws"
    assert env["artifacts"] == "/artifacts"
    assert env["control_location"] == "in_env_control"
    assert env["ownership"] == "fabric_owned"
    assert env["connection"] == {"url": "http://x"}


def test_merge_model_provider_override_applies_when_unset() -> None:
    config = _agent_config()
    spec = EnvironmentSpecInline(
        model_provider_override=ModelProviderOverride(
            base_url="https://api.example.com",
            provider="anthropic",
            api_key="MY_SECRET",
        )
    )
    merged = merge_environment_spec_into_agent_config(config, spec)
    model = merged["models"]["default"]
    assert model["base_url"] == "https://api.example.com"
    assert model["provider"] == "openai"  # Agent's explicit provider wins.
    assert model["api_key_env"] == "MY_SECRET"


def test_merge_mcp_fulfills_by_name_agent_url_wins() -> None:
    config = _agent_config(mcp={"servers": {"search": {"transport": "streamable-http", "url": "http://agent-url"}}})
    spec = EnvironmentSpecInline(
        mcp={
            "search": McpFulfillment(url="http://env-url", env={"E": "1"}, secrets={"TOKEN": "secret-ref"}),
            "new": McpFulfillment(url="http://new-url"),
        }
    )
    merged = merge_environment_spec_into_agent_config(config, spec)
    servers = merged["mcp"]["servers"]
    # Agent-provided url wins; env + secrets merged in.
    assert servers["search"]["url"] == "http://agent-url"
    assert servers["search"]["env"] == {"E": "1", "TOKEN": "secret-ref"}
    # New server contributed entirely by the spec.
    assert servers["new"]["url"] == "http://new-url"


def test_merge_no_environment_reference_is_identical_to_today() -> None:
    # Baseline agent config with no environment merged behaves unchanged.
    config = _agent_config()
    merged = merge_environment_spec_into_agent_config(config, None)
    assert merged == config
