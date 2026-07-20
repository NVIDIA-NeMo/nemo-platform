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

    Mirrors ``nemo_deployments_plugin.types.Endpoint`` so container-mode
    deployments can carry the address the deployments-plugin ``Deployment``
    projected without the agents plugin depending on that plugin at the
    entity-schema layer.
    """

    name: str
    url: str
    protocol: Literal["http", "https", "grpc", "tcp"] = "http"


# ---------------------------------------------------------------------------
# Canonical spec storage convention
# ---------------------------------------------------------------------------
#
# Each agent has exactly one spec fileset, named by convention. The fileset can
# hold both the human-readable agent spec and the machine-readable agent config.
# We do **not** store these locations on the agent - they are fully derivable
# from the agent's workspace and name. Consumers should call the file-ref
# helpers below rather than reconstructing refs inline.
#
# Layout:
#   - Fileset (entity ref):  ``{workspace}/{agent-name}-spec``
#   - Human-readable spec:   ``AGENT-SPEC.md`` (industry-standard name)
#   - Machine-readable cfg:  ``agent.yaml``
#   - Spec file ref:         ``{workspace}/{agent-name}-spec#AGENT-SPEC.md``
#   - Config file ref:       ``{workspace}/{agent-name}-spec#agent.yaml``
#   - Local cache root:      ``agents/{agent-name}-spec/``
#
# This is intentionally **not** an Optional field on the Agent. The
# relationship is 1:1 and convention-bound; carrying a stored ref would
# duplicate state with no resilience benefit (rename of either entity
# orphans both representations equally).

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
    """Return the canonical file ref ``workspace/<name>-spec#AGENT-SPEC.md``.

    Use this anywhere downstream code needs to point at an agent's spec -
    do not reconstruct the path inline. If the layout ever changes (e.g.
    moving to a per-agent bundle fileset holding multiple artifacts), this
    is the only function that needs to update.
    """
    return FilesetRef(f"{workspace}/{agent_spec_fileset_name(agent_name)}#{AGENT_SPEC_FILENAME}")


def agent_config_file_ref(workspace: str, agent_name: str) -> FilesetRef:
    """Return the canonical file ref ``workspace/<name>-spec#agent.yaml``.

    Use this anywhere downstream code needs to point at an agent's config -
    do not reconstruct the path inline. If the layout ever changes (e.g.
    moving to a per-agent bundle fileset holding multiple artifacts), this
    is the only function that needs to update.
    """
    return FilesetRef(f"{workspace}/{agent_spec_fileset_name(agent_name)}#{AGENT_CONFIG_FILENAME}")


# TODO: RFC-122 will add specs for environment, sandbox, and harness. Add those
# specs to this object once finalized.
class Agent(NemoEntity, entity_type="agent"):
    """An agent definition — stores agent config and metadata.

    Entity type: ``agent``
    Primary lookup: by ``name`` within a ``workspace``.

    The agent's spec files live at the locations returned by
    :func:`agent_spec_file_ref` and :func:`agent_config_file_ref` — they
    are **not** stored on the entity because the paths are fully derivable
    from ``(workspace, name)``.
    """

    description: str = Field(default="", description="Human-readable description of the agent.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent config dict interpreted according to config_format.",
    )
    config_format: str = Field(
        default=NAT_WORKFLOW_CONFIG_FORMAT,
        description=(
            "platform-internal schema version tag for the agent config dict. "
            "`nat-workflow-v1` is the default legacy NAT workflow format; "
            "`nemo-agents-spec-v1` identifies the Platform-owned agent.yaml spec format."
        ),
    )


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
