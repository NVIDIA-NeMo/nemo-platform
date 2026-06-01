# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent plugin API schema definitions — request bodies and filters.

This module contains only API-layer Pydantic models.  Entity definitions
(classes stored in the entity store) live in :mod:`nemo_agents_plugin.entities`.

Entity objects (subclasses of :class:`~nemo_platform_plugin.entity.NemoEntity`) are
returned directly from route handlers as the API response — no separate
response model is needed.  Use ``NemoListResponse[Agent]`` /
``NemoListResponse[AgentDeployment]`` for list endpoints.

Naming conventions:
- ``CreateXRequest`` / ``UpdateXRequest`` — plain :class:`~pydantic.BaseModel`
  for request bodies.
- ``XFilter`` — extends :class:`~nemo_platform_plugin.schema.NemoFilter` to inherit
  ``extra="forbid"``.
"""

from __future__ import annotations

from typing import Any

from nemo_agents_plugin.entities import Agent, AgentDeployment, DeploymentStatus
from nemo_platform_plugin.schema import NemoFilter, NemoListResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request bodies — plain BaseModel, named by convention
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    """Request body for ``POST /v2/workspaces/{workspace}/agents``."""

    name: str = Field(description="Unique agent name within the workspace.")
    description: str = Field(default="", description="Human-readable description.")
    config: dict[str, Any] = Field(description="NAT workflow config dict.")
    config_format: str = Field(default="nat-workflow-v1", description="Config format identifier.")


class CreateDeploymentRequest(BaseModel):
    """Request body for ``POST /v2/workspaces/{workspace}/deployments``."""

    agent: str = Field(description="Name of the Agent to deploy.")
    name: str | None = Field(
        default=None,
        description="Optional deployment name.  Auto-generated from agent name + random suffix if omitted.",
    )


# ---------------------------------------------------------------------------
# Filters — extend NemoFilter so extra fields are rejected (extra="forbid")
# ---------------------------------------------------------------------------


class AgentFilter(NemoFilter):
    """Query filter for ``GET /v2/workspaces/{workspace}/agents``."""

    config_format: str | None = Field(
        default=None,
        description="Filter to agents with this config format.",
    )


class DeploymentFilter(NemoFilter):
    """Query filter for ``GET /v2/workspaces/{workspace}/deployments``."""

    agent: str | None = Field(
        default=None,
        description="Filter to deployments for this agent name.",
    )
    status: DeploymentStatus | None = Field(
        default=None,
        description="Filter to deployments in this lifecycle status.",
    )


# ---------------------------------------------------------------------------
# List response type aliases
# ---------------------------------------------------------------------------

AgentPage = NemoListResponse[Agent]
DeploymentPage = NemoListResponse[AgentDeployment]
