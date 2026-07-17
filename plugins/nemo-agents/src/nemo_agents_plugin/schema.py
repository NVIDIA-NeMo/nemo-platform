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
from urllib.parse import urlparse

from nemo_agents_plugin.entities import (
    NAT_WORKFLOW_CONFIG_FORMAT,
    Agent,
    AgentDeployment,
    DeploymentMode,
    DeploymentStatus,
)
from nemo_platform_plugin.schema import NemoFilter, NemoListResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Request bodies — plain BaseModel, named by convention
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    """Request body for ``POST /v2/workspaces/{workspace}/agents``.

    Creates either a **managed** agent (supply ``config`` — a NAT workflow the
    platform will run) or an **external** agent (supply ``url`` — a pointer to
    a NAT agent already running elsewhere, whose A2A card the platform fetches
    at creation). Provide exactly one of ``config`` or ``url``.
    """

    model_config = ConfigDict(json_schema_extra={"oneOf": [{"required": ["config"]}, {"required": ["url"]}]})

    name: str = Field(description="Unique agent name within the workspace.")
    description: str = Field(
        default="",
        description="Human-readable description. For external agents, falls back to the agent card's description.",
    )
    config: dict[str, Any] | None = Field(
        default=None,
        description="NAT workflow config dict. Required for a managed agent; omit for external.",
    )
    config_format: str = Field(default=NAT_WORKFLOW_CONFIG_FORMAT, description="Config format identifier.")
    url: str | None = Field(
        default=None,
        description="Base URL of a running external agent (e.g. http://host:10000). Provide instead of config.",
    )

    @model_validator(mode="after")
    def _require_config_xor_url(self) -> CreateAgentRequest:
        if self.url:
            if self.config is not None:
                raise ValueError("Provide either 'config' (managed agent) or 'url' (external agent), not both.")
            parsed = urlparse(self.url.strip())
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("'url' must be a valid http(s) URL, e.g. http://host:10000.")
        elif self.config is None:
            raise ValueError("'config' is required for a managed agent, or provide 'url' to register an external one.")
        return self


class AgentReachability(BaseModel):
    """Response for ``GET /v2/workspaces/{workspace}/agents/{name}/reachability``."""

    reachable: bool = Field(description="Whether the external agent's endpoint answered a liveness probe.")


class CreateDeploymentRequest(BaseModel):
    """Request body for ``POST /v2/workspaces/{workspace}/deployments``."""

    agent: str = Field(description="Name of the Agent to deploy.")
    name: str | None = Field(
        default=None,
        description="Optional deployment name.  Auto-generated from agent name + random suffix if omitted.",
    )
    deployment_mode: DeploymentMode = Field(
        default="subprocess",
        description="Runtime backend: subprocess (default), docker, or k8s.",
    )
    image: str = Field(
        default="",
        description="Container image for docker/k8s modes. Ignored for subprocess.",
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
