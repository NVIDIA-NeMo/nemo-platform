# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Agents service.

Wraps the endpoint functions from ``agents.endpoints`` as direct methods
using the ``method()`` descriptor, following the files/models pattern.
"""

from nemo_platform_plugin.agents import endpoints
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method


class _AgentsMethods:
    get_agent = method(endpoints.get_agent)
    list_agents = method(endpoints.list_agents)
    create_agent = method(endpoints.create_agent)
    delete_agent = method(endpoints.delete_agent)
    get_deployment = method(endpoints.get_deployment)
    list_deployments = method(endpoints.list_deployments)
    create_deployment = method(endpoints.create_deployment)
    delete_deployment = method(endpoints.delete_deployment)
    invoke_agent = method(endpoints.invoke_agent)
    invoke_deployment = method(endpoints.invoke_deployment)


class AgentsClient(_AgentsMethods, NemoClient):
    """Sync client for the Agents service API."""


class AsyncAgentsClient(_AgentsMethods, AsyncNemoClient):
    """Async client for the Agents service API."""
