# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent entity definitions — stored in the NeMo Platform entity store.

This module contains only entity classes (subclasses of
:class:`~nemo_platform_plugin.entity.NemoEntity`).  API request/response schemas and
filter models live in :mod:`nemo_agents_plugin.schema`.
"""

from __future__ import annotations

from typing import Any, Literal

from nemo_platform_plugin.entity import NemoEntity
from nemo_platform_plugin.refs import FilesetRef
from pydantic import Field

DeploymentStatus = Literal["pending", "starting", "running", "failed", "deleting"]


class Agent(NemoEntity, entity_type="agent"):
    """An agent definition — stores the NAT workflow config and metadata.

    Entity type: ``agent``
    Primary lookup: by ``name`` within a ``workspace``.
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
    spec_file_ref: FilesetRef | None = Field(
        default=None,
        description=(
            "Reference to the fileset holding this agent's spec (AGENTSpec.md). "
            "Set by ``nemo-spec`` when the spec is uploaded, then carried forward by "
            "``nemo agents create``. Optional: agents created via the CLI without an "
            "onboarding skill will leave this empty, which is queryable ("
            "'show me agents with no spec')."
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
