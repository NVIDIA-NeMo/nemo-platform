# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the deployments-plugin API.

Wraps the ``deployments.endpoints`` functions as methods via the ``method()``
descriptor (the Files/Secrets/Jobs pattern), plus ergonomic
``create_*``/``get_*``/``list_*``/``delete_*`` helpers that return unwrapped
models. ``delete_*`` is a soft-delete (see ``endpoints``): it returns ``None``
and the caller polls ``get_*`` for teardown.

Usage::

    from nemo_platform_plugin.deployments.client import DeploymentsClient
    from nemo_platform_plugin.deployments.types import CreateVolumeRequest

    client = DeploymentsClient(base_url="...", workspace="default")
    vol = client.create_volume(body=CreateVolumeRequest(name="weights")).data()
    for v in client.list_volumes().items():
        print(v.name, v.status)
    client.delete_volume(name="weights")
"""

from __future__ import annotations

import builtins

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.deployments import endpoints
from nemo_platform_plugin.deployments.types import (
    CreateDeploymentConfigRequest,
    CreateDeploymentRequest,
    CreateVolumeRequest,
    Deployment,
    DeploymentConfig,
    ListDeploymentConfigsQueryParams,
    ListDeploymentsQueryParams,
    ListVolumesQueryParams,
    Volume,
)


class _DeploymentsMethods:
    # Volumes
    create_volume = method(endpoints.create_volume)
    list_volumes = method(endpoints.list_volumes)
    get_volume = method(endpoints.get_volume)
    delete_volume = method(endpoints.delete_volume)

    # Deployment configs
    create_deployment_config = method(endpoints.create_deployment_config)
    list_deployment_configs = method(endpoints.list_deployment_configs)
    get_deployment_config = method(endpoints.get_deployment_config)
    delete_deployment_config = method(endpoints.delete_deployment_config)

    # Deployments
    create_deployment = method(endpoints.create_deployment)
    list_deployments = method(endpoints.list_deployments)
    get_deployment = method(endpoints.get_deployment)
    delete_deployment = method(endpoints.delete_deployment)


class DeploymentsClient(_DeploymentsMethods, NemoClient):
    """Sync client for the deployments-plugin API."""

    # --- Volumes ---
    def create(self, body: CreateVolumeRequest, *, workspace: str | None = None, exist_ok: bool = False) -> Volume:
        return self.create_volume(workspace=workspace, body=body, exist_ok=exist_ok).data()

    def get(self, name: str, *, workspace: str | None = None) -> Volume:
        return self.get_volume(name=name, workspace=workspace).data()

    def list(
        self, *, workspace: str | None = None, query_params: ListVolumesQueryParams | None = None
    ) -> builtins.list[Volume]:
        return list(self.list_volumes(workspace=workspace, query_params=query_params).items())

    def delete(self, name: str, *, workspace: str | None = None) -> None:
        self.delete_volume(name=name, workspace=workspace).data()

    # --- Deployment configs ---
    def create_config(
        self, body: CreateDeploymentConfigRequest, *, workspace: str | None = None, exist_ok: bool = False
    ) -> DeploymentConfig:
        return self.create_deployment_config(workspace=workspace, body=body, exist_ok=exist_ok).data()

    def get_config(self, name: str, *, workspace: str | None = None) -> DeploymentConfig:
        return self.get_deployment_config(name=name, workspace=workspace).data()

    def list_configs(
        self, *, workspace: str | None = None, query_params: ListDeploymentConfigsQueryParams | None = None
    ) -> builtins.list[DeploymentConfig]:
        return list(self.list_deployment_configs(workspace=workspace, query_params=query_params).items())

    def delete_config(self, name: str, *, workspace: str | None = None) -> None:
        self.delete_deployment_config(name=name, workspace=workspace).data()

    # --- Deployments ---
    def create_deploy(
        self, body: CreateDeploymentRequest, *, workspace: str | None = None, exist_ok: bool = False
    ) -> Deployment:
        return self.create_deployment(workspace=workspace, body=body, exist_ok=exist_ok).data()

    def get_deploy(self, name: str, *, workspace: str | None = None) -> Deployment:
        return self.get_deployment(name=name, workspace=workspace).data()

    def list_deploys(
        self, *, workspace: str | None = None, query_params: ListDeploymentsQueryParams | None = None
    ) -> builtins.list[Deployment]:
        return list(self.list_deployments(workspace=workspace, query_params=query_params).items())

    def delete_deploy(self, name: str, *, workspace: str | None = None) -> None:
        self.delete_deployment(name=name, workspace=workspace).data()


class AsyncDeploymentsClient(_DeploymentsMethods, AsyncNemoClient):
    """Async client for the deployments-plugin API."""

    # --- Volumes ---
    async def create(
        self, body: CreateVolumeRequest, *, workspace: str | None = None, exist_ok: bool = False
    ) -> Volume:
        return (await self.create_volume(workspace=workspace, body=body, exist_ok=exist_ok)).data()

    async def get(self, name: str, *, workspace: str | None = None) -> Volume:
        return (await self.get_volume(name=name, workspace=workspace)).data()

    async def list(
        self, *, workspace: str | None = None, query_params: ListVolumesQueryParams | None = None
    ) -> builtins.list[Volume]:
        response = await self.list_volumes(workspace=workspace, query_params=query_params)
        return [item async for item in response.items()]

    async def delete(self, name: str, *, workspace: str | None = None) -> None:
        (await self.delete_volume(name=name, workspace=workspace)).data()

    # --- Deployment configs ---
    async def create_config(
        self, body: CreateDeploymentConfigRequest, *, workspace: str | None = None, exist_ok: bool = False
    ) -> DeploymentConfig:
        return (await self.create_deployment_config(workspace=workspace, body=body, exist_ok=exist_ok)).data()

    async def get_config(self, name: str, *, workspace: str | None = None) -> DeploymentConfig:
        return (await self.get_deployment_config(name=name, workspace=workspace)).data()

    async def list_configs(
        self, *, workspace: str | None = None, query_params: ListDeploymentConfigsQueryParams | None = None
    ) -> builtins.list[DeploymentConfig]:
        response = await self.list_deployment_configs(workspace=workspace, query_params=query_params)
        return [item async for item in response.items()]

    async def delete_config(self, name: str, *, workspace: str | None = None) -> None:
        (await self.delete_deployment_config(name=name, workspace=workspace)).data()

    # --- Deployments ---
    async def create_deploy(
        self, body: CreateDeploymentRequest, *, workspace: str | None = None, exist_ok: bool = False
    ) -> Deployment:
        return (await self.create_deployment(workspace=workspace, body=body, exist_ok=exist_ok)).data()

    async def get_deploy(self, name: str, *, workspace: str | None = None) -> Deployment:
        return (await self.get_deployment(name=name, workspace=workspace)).data()

    async def list_deploys(
        self, *, workspace: str | None = None, query_params: ListDeploymentsQueryParams | None = None
    ) -> builtins.list[Deployment]:
        response = await self.list_deployments(workspace=workspace, query_params=query_params)
        return [item async for item in response.items()]

    async def delete_deploy(self, name: str, *, workspace: str | None = None) -> None:
        (await self.delete_deployment(name=name, workspace=workspace)).data()
