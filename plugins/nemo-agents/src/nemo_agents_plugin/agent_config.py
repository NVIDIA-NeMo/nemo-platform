# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Platform-owned agent.yaml config models for NeMo Agents.

These models back Agent.config when config_format is nemo-agents-spec-v1.
RFC122 proposes first-class environment_spec, sandbox_spec, and harness_spec
fields on Agent; until those shapes are finalized, this config keeps those
inputs together in the versioned Agent.config payload and can be migrated once
the RFC122 contract lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Self

import yaml
from nemo_agents_plugin.entities import AGENT_CONFIG_FILENAME
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class AgentConfigLoadError(ValueError):
    """Raised when a Platform-owned agent.yaml cannot be loaded."""


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    api_key_env: str | None = None
    temperature: float | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class HarnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    model: ModelConfig | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class EnvironmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "local"
    workspace: str = "./workspace"
    artifacts: str = "./artifacts"
    settings: dict[str, Any] = Field(default_factory=dict)


class TelemetryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str | None = None
    output_dir: str | None = None
    project: str | None = None
    atif: dict[str, Any] | None = None
    atof: dict[str, Any] | None = None


class MCPServerConfig(BaseModel):
    """Platform-owned MCP server configuration."""

    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio", "http", "streamable-http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    exposure: Literal["harness_native", "fabric_managed"] = "harness_native"

    @model_validator(mode="after")
    def _validate_transport_target(self) -> Self:
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio MCP servers require command")
            if self.url is not None:
                raise ValueError("stdio MCP servers do not accept url")
        else:
            if not self.url:
                raise ValueError(f"{self.transport} MCP servers require url")
            if self.command is not None or self.args:
                raise ValueError(f"{self.transport} MCP servers do not accept command or args")
        return self


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_server_names(self) -> Self:
        if any(not name.strip() for name in self.servers):
            raise ValueError("MCP server names must not be empty")
        return self


class AgentConfig(BaseModel):
    """Platform-owned agent.yaml config for nemo-agents-spec-v1."""

    model_config = ConfigDict(extra="forbid")

    config_format: Literal["nemo-agents-spec-v1"]
    name: str
    description: str = ""
    default_harness: str
    harnesses: dict[str, HarnessConfig]
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)
    skills: dict[str, Any] | list[Any] | None = None
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    @model_validator(mode="after")
    def _validate_default_harness(self) -> Self:
        if self.default_harness not in self.harnesses:
            available = ", ".join(sorted(self.harnesses))
            raise ValueError(f"default_harness must reference one of harnesses: {available}")
        return self


class AgentProfileConfig(BaseModel):
    """A named overlay applied to a Platform-owned agent config."""

    model_config = ConfigDict(extra="forbid")

    profile_format: Literal["nemo-agents-profile-v1"]
    name: str = Field(min_length=1)
    mcp: MCPConfig | None = None


def apply_agent_profiles(config: AgentConfig, profiles: list[AgentProfileConfig]) -> AgentConfig:
    """Apply profile overlays in order, with later profiles taking precedence."""
    resolved = config.model_copy(deep=True)
    for profile in profiles:
        if profile.mcp is not None:
            resolved.mcp = profile.mcp.model_copy(deep=True)
    return resolved


def load_agent_profile(path: str | Path) -> AgentProfileConfig:
    """Load a Platform-owned agent profile YAML file."""
    profile_path = Path(path)

    try:
        raw_profile = profile_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AgentConfigLoadError(f"Unable to read agent profile {profile_path}: {error}") from error
    except UnicodeDecodeError as error:
        raise AgentConfigLoadError(f"Agent profile {profile_path} is not valid UTF-8: {error}") from error

    try:
        data = yaml.safe_load(raw_profile)
    except yaml.YAMLError as error:
        raise AgentConfigLoadError(f"YAML parse error in agent profile {profile_path}: {error}") from error

    if not isinstance(data, dict):
        raise AgentConfigLoadError(f"Agent profile {profile_path} root must be a YAML mapping.")

    try:
        return AgentProfileConfig.model_validate(data)
    except ValidationError as error:
        raise AgentConfigLoadError(f"Invalid agent profile {profile_path}: {error}") from error


def load_agent_config(path: str | Path) -> AgentConfig:
    """Load a Platform-owned agent.yaml file as an AgentConfig."""
    config_path = Path(path)

    try:
        raw_config = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AgentConfigLoadError(f"Unable to read agent config {config_path}: {error}") from error
    except UnicodeDecodeError as error:
        raise AgentConfigLoadError(f"Agent config {config_path} is not valid UTF-8: {error}") from error

    try:
        data = yaml.safe_load(raw_config)
    except yaml.YAMLError as error:
        raise AgentConfigLoadError(f"YAML parse error in agent config {config_path}: {error}") from error

    if not isinstance(data, dict):
        raise AgentConfigLoadError(f"Agent config {config_path} root must be a YAML mapping.")

    try:
        return AgentConfig.model_validate(data)
    except ValidationError as error:
        raise AgentConfigLoadError(f"Invalid agent config {config_path}: {error}") from error


def load_agent_config_from_dir(agent_dir: str | Path) -> AgentConfig:
    """Load the canonical agent.yaml file from an agent directory."""
    return load_agent_config(Path(agent_dir) / AGENT_CONFIG_FILENAME)
