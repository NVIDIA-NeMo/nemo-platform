# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the Agents service.

Single source of truth for the HTTP contract. Replaces the Stainless-generated
agent resource from ``nemo_agents_plugin.sdk``.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from nemo_platform_plugin.agents.types import (
    Agent,
    AgentDeployment,
    CreateAgentDeploymentRequest,
    CreateAgentRequest,
    InvokeAgentRequest,
    ListAgentsQueryParams,
    ListDeploymentsQueryParams,
)
from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.types import Paginated, PreparedRequest

_AGENTS = "/apis/agents/v2/workspaces/{workspace}/agents"
_DEPLOYMENTS = "/apis/agents/v2/workspaces/{workspace}/deployments"


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------


@get(f"{_AGENTS}/{{name}}")
@abstractmethod
def get_agent(*, workspace: str | None = None, name: str) -> Agent: ...


@get(_AGENTS)
@abstractmethod
def list_agents(
    *, workspace: str | None = None, query_params: ListAgentsQueryParams | None = None
) -> Paginated[Agent]: ...


def _get_agent_on_conflict(body: CreateAgentRequest, workspace: str | None) -> PreparedRequest[Agent]:
    """Build the retrieve request replayed when ``create_agent(exist_ok=True)`` 409s."""
    return get_agent(name=body.name, workspace=workspace)


@post(_AGENTS, get_on_conflict=_get_agent_on_conflict)
@abstractmethod
def create_agent(*, workspace: str | None = None, body: CreateAgentRequest, exist_ok: bool = False) -> Agent: ...


@delete(f"{_AGENTS}/{{name}}")
@abstractmethod
def delete_agent(*, workspace: str | None = None, name: str) -> None: ...


# ---------------------------------------------------------------------------
# Agent deployment CRUD
# ---------------------------------------------------------------------------


@get(f"{_DEPLOYMENTS}/{{name}}")
@abstractmethod
def get_deployment(*, workspace: str | None = None, name: str) -> AgentDeployment: ...


@get(_DEPLOYMENTS)
@abstractmethod
def list_deployments(
    *, workspace: str | None = None, query_params: ListDeploymentsQueryParams | None = None
) -> Paginated[AgentDeployment]: ...


@post(_DEPLOYMENTS)
@abstractmethod
def create_deployment(*, workspace: str | None = None, body: CreateAgentDeploymentRequest) -> AgentDeployment: ...


@delete(f"{_DEPLOYMENTS}/{{name}}")
@abstractmethod
def delete_deployment(*, workspace: str | None = None, name: str) -> None: ...


# ---------------------------------------------------------------------------
# Agent invocation (gateway proxy to OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------


@post(f"{_AGENTS}/{{name}}/-/v1/chat/completions")
@abstractmethod
def invoke_agent(*, workspace: str | None = None, name: str, body: InvokeAgentRequest) -> dict[str, Any]: ...


@post(f"{_DEPLOYMENTS}/{{name}}/-/v1/chat/completions")
@abstractmethod
def invoke_deployment(*, workspace: str | None = None, name: str, body: InvokeAgentRequest) -> dict[str, Any]: ...
