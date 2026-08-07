# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public manifest describing a served Fabric agent's operational contract.

The manifest is an allowlist projection of :class:`AgentConfig`, never a dump.
It is served unauthenticated, so a field reaches it only by being named here.
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import PurePath
from typing import Literal

from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.serving_models import SESSION_ID_HEADER
from pydantic import BaseModel, Field

MANIFEST_SCHEMA_VERSION = "nemo-agent-manifest/v1"

_FABRIC_DISTRIBUTION = "nemo-fabric"


class ManifestAgent(BaseModel):
    """Identity of the served agent."""

    name: str
    description: str = ""
    revision: str


class ManifestHarness(BaseModel):
    """Harness driving the agent."""

    kind: str


class ManifestRuntime(BaseModel):
    """Runtime executing the agent."""

    harness: ManifestHarness
    fabric_version: str | None = None


class ManifestSessions(BaseModel):
    """How the server scopes conversation state."""

    header: str = SESSION_ID_HEADER
    default: Literal["ephemeral"] = "ephemeral"


class ManifestServing(BaseModel):
    """Invocation contract a caller must respect."""

    protocol: Literal["openai-chat-completions"] = "openai-chat-completions"
    streaming: bool = True
    sessions: ManifestSessions = Field(default_factory=ManifestSessions)
    max_concurrent_invocations: int


class ManifestEnvironment(BaseModel):
    """Environment the agent executes in.

    ``workspace_scope`` is ``agent`` when one workspace is shared by every
    session, which means invocations are not isolated from each other.
    """

    provider: str
    workspace_scope: Literal["agent", "session"]


class ManifestMcpServer(BaseModel):
    """An MCP server the agent can reach, by name only."""

    name: str
    transport: str
    exposure: str


class ManifestCapabilities(BaseModel):
    """What the agent can do, by name."""

    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[ManifestMcpServer] = Field(default_factory=list)
    tools_blocked: list[str] = Field(default_factory=list)


class ManifestModel(BaseModel):
    """A model the agent is configured to call."""

    alias: str
    provider: str
    model: str


class ManifestTelemetry(BaseModel):
    """Whether the agent already emits its own traces."""

    emits: bool
    formats: list[str] = Field(default_factory=list)


class ManifestTunable(BaseModel):
    """Knob names an optimizer may sweep. Names only, never values."""

    prompts: list[str] = Field(default_factory=list)
    harness_settings: list[str] = Field(default_factory=list)


class AgentManifest(BaseModel):
    """Operational contract published at ``GET /manifest``."""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    agent: ManifestAgent
    runtime: ManifestRuntime
    serving: ManifestServing
    environment: ManifestEnvironment
    capabilities: ManifestCapabilities
    models: list[ManifestModel] = Field(default_factory=list)
    telemetry: ManifestTelemetry
    tunable: ManifestTunable


def build_agent_manifest(config: AgentConfig, *, max_concurrent_invocations: int) -> AgentManifest:
    """Project an agent config into its public manifest."""
    manifest = AgentManifest(
        agent=ManifestAgent(name=config.name, description=config.description, revision=""),
        runtime=_runtime(config),
        serving=ManifestServing(max_concurrent_invocations=max_concurrent_invocations),
        environment=ManifestEnvironment(provider=config.environment.provider, workspace_scope="agent"),
        capabilities=_capabilities(config),
        models=_models(config),
        telemetry=_telemetry(config),
        tunable=_tunable(config),
    )
    return _stamp_revision(manifest)


def _runtime(config: AgentConfig) -> ManifestRuntime:
    harness = config.harnesses[config.default_harness]
    return ManifestRuntime(harness=ManifestHarness(kind=harness.kind), fabric_version=_fabric_version())


def _fabric_version() -> str | None:
    try:
        return version(_FABRIC_DISTRIBUTION)
    except PackageNotFoundError:
        return None


def _capabilities(config: AgentConfig) -> ManifestCapabilities:
    servers = config.mcp.servers if config.mcp else {}
    return ManifestCapabilities(
        skills=_skill_names(config),
        mcp_servers=[
            ManifestMcpServer(name=name, transport=server.transport, exposure=server.exposure)
            for name, server in sorted(servers.items())
        ],
        tools_blocked=sorted(config.tools.blocked) if config.tools else [],
    )


def _skill_names(config: AgentConfig) -> list[str]:
    """Skill directory names, never the host paths they were loaded from."""
    if config.skills is None:
        return []

    names: list[str] = []
    for path in config.skills.paths:
        name = PurePath(path).name
        if name and name not in names:
            names.append(name)
    return names


def _models(config: AgentConfig) -> list[ManifestModel]:
    models = [
        ManifestModel(alias=alias, provider=model.provider, model=model.model)
        for alias, model in sorted(config.models.items())
    ]
    models.extend(
        ManifestModel(alias=f"harness:{name}", provider=harness.model.provider, model=harness.model.model)
        for name, harness in sorted(config.harnesses.items())
        if harness.model is not None
    )
    return models


def _telemetry(config: AgentConfig) -> ManifestTelemetry:
    telemetry = config.telemetry
    formats = [name for name, payload in (("atif", telemetry.atif), ("atof", telemetry.atof)) if payload is not None]
    return ManifestTelemetry(emits=telemetry.enabled, formats=formats)


def _tunable(config: AgentConfig) -> ManifestTunable:
    harness = config.harnesses[config.default_harness]
    return ManifestTunable(prompts=sorted(config.prompts), harness_settings=sorted(harness.settings))


def _stamp_revision(manifest: AgentManifest) -> AgentManifest:
    """Fingerprint the redacted projection, so the hash cannot leak what it omits."""
    payload = manifest.model_dump(mode="json")
    payload["agent"].pop("revision", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    revision = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    return manifest.model_copy(update={"agent": manifest.agent.model_copy(update={"revision": revision})})
