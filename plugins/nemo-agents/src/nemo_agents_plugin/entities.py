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
from pydantic import Field

DeploymentStatus = Literal["pending", "starting", "running", "failed", "deleting"]


# ---------------------------------------------------------------------------
# Canonical spec storage convention
# ---------------------------------------------------------------------------
#
# Each agent has exactly one spec, named by convention. We do **not** store
# the spec location on the agent — it is fully derivable from the agent's
# workspace and name. The convention is enforced by the nemo-spec and
# nemo-build-agent skills; consumers (analyst agent, Studio, optimization
# loop) should call :func:`agent_spec_file_ref` rather than reconstruct the
# path inline.
#
# Layout:
#   - Fileset (entity ref):  ``{workspace}/{agent-name}-spec``
#   - File inside fileset:   ``AGENT-SPEC.md`` (industry-standard name)
#   - Full file ref:         ``{workspace}/{agent-name}-spec#AGENT-SPEC.md``
#   - Local cache:           ``agents/{agent-name}-spec/AGENT-SPEC.md``
#
# This is intentionally **not** an Optional field on the Agent. The
# relationship is 1:1 and convention-bound; carrying a stored ref would
# duplicate state with no resilience benefit (rename of either entity
# orphans both representations equally).

AGENT_SPEC_FILENAME = "AGENT-SPEC.md"
"""Canonical filename inside the agent's spec fileset."""


AGENT_SPEC_LOCAL_ROOT = "agents"
"""Local directory holding agent build artifacts."""


def agent_spec_fileset_name(agent_name: str) -> str:
    """Return the conventional fileset name holding an agent's spec."""
    return f"{agent_name}-spec"


def agent_spec_local_path(agent_name: str, root: str | Path = AGENT_SPEC_LOCAL_ROOT) -> Path:
    """Return the local write-through cache path for an agent's spec."""
    return Path(root) / agent_spec_fileset_name(agent_name) / AGENT_SPEC_FILENAME


def agent_spec_file_ref(workspace: str, agent_name: str) -> FilesetRef:
    """Return the canonical file ref ``workspace/<name>-spec#AGENT-SPEC.md``.

    Use this anywhere downstream code needs to point at an agent's spec —
    do not reconstruct the path inline. If the layout ever changes (e.g.
    moving to a per-agent bundle fileset holding multiple artifacts), this
    is the only function that needs to update.
    """
    return FilesetRef(f"{workspace}/{agent_spec_fileset_name(agent_name)}#{AGENT_SPEC_FILENAME}")


class Agent(NemoEntity, entity_type="agent"):
    """An agent definition — stores the NAT workflow config and metadata.

    Entity type: ``agent``
    Primary lookup: by ``name`` within a ``workspace``.

    The agent's spec lives at the location returned by
    :func:`agent_spec_file_ref` — it is **not** stored on the entity
    because the path is fully derivable from ``(workspace, name)``.
    """

    description: str = Field(default="", description="Human-readable description of the agent.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="NAT workflow config (YAML-equivalent dict, keyed by component name).",
    )
    config_format: str = Field(
        default="nat-workflow-v1",
        description=(
            "platform-internal schema version tag for the agent config dict.  "
            "Not read or validated by NAT — used by NeMo Platform for future config migration.  "
            "Currently only 'nat-workflow-v1' is supported."
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
    endpoint: str = Field(
        default="", description="HTTP endpoint of the running agent process (e.g. http://localhost:9001)."
    )
    port: int = Field(default=0, description="Port the agent process is listening on.")
    pid: int = Field(default=0, description="OS process ID of the agent subprocess.")
    error: str = Field(default="", description="Error message if status is 'failed'.")
