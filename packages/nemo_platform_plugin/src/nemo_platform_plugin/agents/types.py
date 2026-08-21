# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Agents service.

Single source of truth for the HTTP contract. Replaces the Stainless-generated
agent resource from ``nemo_agents_plugin.sdk``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from nemo_platform_plugin.schema import Page
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


class Agent(BaseModel):
    """An agent definition — stores agent config and metadata."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str = ""
    project: str | None = None
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    config_format: str = "nat-workflow-v1"
    id: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


AgentPage = Page[Agent]


class AgentDeployment(BaseModel):
    """A running (or pending) deployment of an Agent."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str = ""
    project: str | None = None
    agent: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    deployment_mode: str = "subprocess"
    endpoint: str = ""
    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


DeploymentPage = Page[AgentDeployment]


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------


class CreateAgentRequest(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    config_format: str = "nat-workflow-v1"


class CreateAgentDeploymentRequest(BaseModel):
    agent: str
    config: dict[str, Any] = Field(default_factory=dict)


class InvokeAgentRequest(BaseModel):
    """OpenAI chat-completions request body for agent invocation."""

    model_config = ConfigDict(extra="allow")

    messages: list[dict[str, Any]] = Field(default_factory=list)
    stream: bool = False


# ---------------------------------------------------------------------------
# Query parameter types
# ---------------------------------------------------------------------------


class ListAgentsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]


class ListDeploymentsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]
