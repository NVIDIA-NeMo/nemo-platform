# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Agents service.

Wraps the endpoint functions from ``agents.endpoints`` as direct methods
using the ``method()`` descriptor, following the files/models pattern.
"""

from functools import cached_property

from nemo_platform_plugin.agents import endpoints
from nemo_platform_plugin.agents.types import CreateExecuteJobRequest, JsonObject
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
    create_execute_job = method(endpoints.create_execute_job)
    get_execute_job = method(endpoints.get_execute_job)
    list_execute_job_results = method(endpoints.list_execute_job_results)


class _ExecuteJobsCompat:
    def __init__(self, client: "AgentsClient") -> None:
        self._client = client

    def create(
        self,
        *,
        spec: JsonObject,
        name: str | None = None,
        description: str | None = None,
        workspace: str | None = None,
    ) -> JsonObject:
        return self._client.create_execute_job(
            workspace=workspace,
            body=CreateExecuteJobRequest(spec=spec, name=name, description=description),
        ).data()

    def get(self, name: str, *, workspace: str | None = None) -> JsonObject:
        return self._client.get_execute_job(name=name, workspace=workspace).data()

    def list_results(self, name: str, *, workspace: str | None = None) -> JsonObject:
        return self._client.list_execute_job_results(name=name, workspace=workspace).data()


class _AsyncExecuteJobsCompat:
    def __init__(self, client: "AsyncAgentsClient") -> None:
        self._client = client

    async def create(
        self,
        *,
        spec: JsonObject,
        name: str | None = None,
        description: str | None = None,
        workspace: str | None = None,
    ) -> JsonObject:
        response = await self._client.create_execute_job(
            workspace=workspace,
            body=CreateExecuteJobRequest(spec=spec, name=name, description=description),
        )
        return response.data()

    async def get(self, name: str, *, workspace: str | None = None) -> JsonObject:
        return (await self._client.get_execute_job(name=name, workspace=workspace)).data()

    async def list_results(self, name: str, *, workspace: str | None = None) -> JsonObject:
        return (await self._client.list_execute_job_results(name=name, workspace=workspace)).data()


class _JobsCompat:
    def __init__(self, client: "AgentsClient") -> None:
        self._client = client

    @cached_property
    def execute(self) -> _ExecuteJobsCompat:
        return _ExecuteJobsCompat(self._client)


class _AsyncJobsCompat:
    def __init__(self, client: "AsyncAgentsClient") -> None:
        self._client = client

    @cached_property
    def execute(self) -> _AsyncExecuteJobsCompat:
        return _AsyncExecuteJobsCompat(self._client)


class AgentsClient(_AgentsMethods, NemoClient):
    """Sync client for the Agents service API."""

    @cached_property
    def jobs(self) -> _JobsCompat:
        return _JobsCompat(self)


class AsyncAgentsClient(_AgentsMethods, AsyncNemoClient):
    """Async client for the Agents service API."""

    @cached_property
    def jobs(self) -> _AsyncJobsCompat:
        return _AsyncJobsCompat(self)
