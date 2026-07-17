# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent entity definitions — stored in the NeMo Platform entity store.

This module contains only entity classes (subclasses of
:class:`~nemo_platform_plugin.entity.NemoEntity`).  API request/response schemas and
filter models live in :mod:`nemo_agents_plugin.schema`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from nemo_platform_plugin.entity import NemoEntity
from nemo_platform_plugin.refs import FilesetRef
from pydantic import BaseModel, Field

DeploymentStatus = Literal["pending", "starting", "running", "failed", "deleting"]

# Where an agent's runtime lives. ``managed`` agents are run by NeMo Platform
# (config compiled to a ``nat serve`` deployment). ``external`` agents run
# outside the platform; NMP only holds a pointer (``endpoint``) plus the A2A
# agent card fetched at registration time — it never spawns them.
AgentSource = Literal["managed", "external"]

# Runtime backend for an AgentDeployment. ``subprocess`` (the default) runs the
# agent as a local ``nat serve`` process reachable on a loopback ``endpoint``.
# ``docker``/``k8s`` run the agent as a durable container deployment via the
# deployments plugin; their routable address is projected onto ``endpoints``.
DeploymentMode = Literal["subprocess", "docker", "k8s"]

# Modes that compile to the nemo-deployments plugin (not local subprocess).
CONTAINER_DEPLOYMENT_MODES: frozenset[str] = frozenset({"docker", "k8s"})


def is_container_deployment_mode(mode: str) -> bool:
    """Return True when *mode* uses the deployments-plugin runner backend."""
    return mode in CONTAINER_DEPLOYMENT_MODES


class Endpoint(BaseModel):
    """A routable network endpoint for a deployment.

    Mirrors ``nemo_deployments_plugin.types.Endpoint`` so the agents plugin need not
    depend on the deployments plugin at the entity-schema layer.
    """

    name: str
    url: str
    protocol: Literal["http", "https", "grpc", "tcp"] = "http"


# Each agent has one spec fileset (``{workspace}/{name}-spec``) holding the human spec
# and the machine config. Locations are derivable from (workspace, name), so they aren't
# stored on the agent; call the file-ref helpers below rather than rebuilding refs inline.
AGENT_SPEC_FILENAME = "AGENT-SPEC.md"
"""Canonical filename inside the agent's spec fileset."""

AGENT_CONFIG_FILENAME = "agent.yaml"
"""Canonical machine-readable agent config filename in the agent spec fileset.

This file is parsed into Agent.config when using the nemo-agents-spec-v1 format.
"""

AGENT_SPEC_LOCAL_ROOT = "agents"
"""Local directory holding agent build artifacts."""

NAT_WORKFLOW_CONFIG_FORMAT = "nat-workflow-v1"
"""Canonical format tag for the legacy NAT workflow config format."""

NEMO_AGENTS_SPEC_CONFIG_FORMAT = "nemo-agents-spec-v1"
"""Canonical format tag for the Platform-owned agent.yaml spec format."""


def agent_spec_fileset_name(agent_name: str) -> str:
    """Return the conventional fileset name holding an agent's spec."""
    return f"{agent_name}-spec"


def agent_spec_local_path(agent_name: str, root: str | Path = AGENT_SPEC_LOCAL_ROOT) -> Path:
    """Return the local write-through cache path for an agent's spec."""
    return Path(root) / agent_spec_fileset_name(agent_name) / AGENT_SPEC_FILENAME


def agent_spec_file_ref(workspace: str, agent_name: str) -> FilesetRef:
    """Return the canonical file ref ``workspace/<name>-spec#AGENT-SPEC.md``."""
    return FilesetRef(f"{workspace}/{agent_spec_fileset_name(agent_name)}#{AGENT_SPEC_FILENAME}")


def agent_config_file_ref(workspace: str, agent_name: str) -> FilesetRef:
    """Return the canonical file ref ``workspace/<name>-spec#agent.yaml``."""
    return FilesetRef(f"{workspace}/{agent_spec_fileset_name(agent_name)}#{AGENT_CONFIG_FILENAME}")


# TODO: RFC-122 will add specs for environment, sandbox, and harness. Add those
# specs to this object once finalized.
class Agent(NemoEntity, entity_type="agent"):
    """An agent definition — stores agent config and metadata.

    Entity type: ``agent``
    Primary lookup: by ``name`` within a ``workspace``.

    Spec files live at :func:`agent_spec_file_ref` / :func:`agent_config_file_ref`;
    the paths aren't stored on the entity since they derive from ``(workspace, name)``.
    """

    description: str = Field(default="", description="Human-readable description of the agent.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent config dict interpreted according to config_format. Empty for external agents.",
    )
    config_format: str = Field(
        default=NAT_WORKFLOW_CONFIG_FORMAT,
        description=(
            "platform-internal schema version tag for the agent config dict. "
            "`nat-workflow-v1` is the default legacy NAT workflow format; "
            "`nemo-agents-spec-v1` identifies the Platform-owned agent.yaml spec format."
        ),
    )
    source: AgentSource = Field(
        default="managed",
        description=(
            "'managed' (default) agents are deployed and run by NeMo Platform. "
            "'external' agents run outside the platform; NMP holds only a pointer to them."
        ),
    )
    endpoint: str = Field(
        default="",
        description=(
            "Base URL of an external agent (e.g. http://host:10000). Empty for managed "
            "agents, whose runtime address lives on the AgentDeployment instead."
        ),
    )
    card: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "A2A agent card fetched from an external agent at registration "
            "(name, description, skills). Empty for managed agents."
        ),
    )


def is_external_agent(agent: Agent) -> bool:
    """Return True when *agent* runs outside NeMo Platform (``source == 'external'``)."""
    return agent.source == "external"


class AgentDeployment(NemoEntity, entity_type="agent_deployment"):
    """A running (or pending) deployment of an Agent.

    Entity type: ``agent_deployment``
    Lifecycle: pending → starting → running | failed.
    The :class:`~nemo_agents_plugin.runner.controller.AgentDeploymentController`
    drives state transitions by reconciling this entity against the
    :class:`~nemo_agents_plugin.runner.backend.RunnerBackend`.
    """

    agent: str = Field(default="", description="Name of the Agent entity this deployment is for.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved agent config with IGW URL injected, written when the deployment is created.",
    )
    status: DeploymentStatus = Field(
        default="pending",
        description="Lifecycle status: pending | starting | running | failed | deleting.",
    )
    deployment_mode: DeploymentMode = Field(
        default="subprocess",
        description=(
            "Runtime backend for this deployment. 'subprocess' (default) reads the loopback "
            "'endpoint'; 'docker'/'k8s' read the projected 'endpoints'."
        ),
    )
    # Dual addressing: subprocess uses loopback ``endpoint``; docker/k8s project
    # routable addresses onto ``endpoints`` and leave ``endpoint`` empty.
    endpoint: str = Field(
        default="", description="Subprocess loopback endpoint of the agent process (e.g. http://localhost:9001)."
    )
    endpoints: list[Endpoint] = Field(
        default_factory=list,
        description=(
            "Routable endpoints for container modes, projected from the deployments-plugin "
            "Deployment. Empty for subprocess mode (which uses 'endpoint')."
        ),
    )
    image: str = Field(
        default="",
        description="Container image for docker/k8s modes. Empty for subprocess; falls back to AgentsConfig.deployments.default_image.",
    )
    plugin_deployment: str = Field(
        default="",
        description=(
            "Name of the linked nemo-deployments Deployment entity. Defaults to this "
            "deployment's name when empty (set by the controller on create)."
        ),
    )
    port: int = Field(default=0, description="Port the agent process is listening on.")
    pid: int = Field(default=0, description="OS process ID of the agent subprocess.")
    error: str = Field(default="", description="Error message if status is 'failed'.")
