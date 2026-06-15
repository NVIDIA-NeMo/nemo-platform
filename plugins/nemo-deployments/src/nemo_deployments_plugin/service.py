# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployments plugin service registration."""

from __future__ import annotations

import logging
from typing import ClassVar

from nemo_deployments_plugin.backends.registry import ExecutorRegistry, ExecutorSpec
from nemo_deployments_plugin.config import DeploymentsConfig
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.authz import AuthzContribution, AuthzEndpointMethod
from nemo_platform_plugin.sdk_provider import get_async_platform_sdk
from nemo_platform_plugin.service import NemoService, RouterSpec

logger = logging.getLogger(__name__)

_SERVICE_NAME = "deployments"
_READ_SCOPES = [f"{_SERVICE_NAME}:read", "platform:read"]
_WRITE_SCOPES = [f"{_SERVICE_NAME}:write", "platform:write"]


def _read_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_READ_SCOPES))


def _write_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_WRITE_SCOPES))


def _read_methods(permission: str) -> dict[str, AuthzEndpointMethod]:
    return {method: _read_method(permission) for method in ("get", "head")}


class DeploymentsService(NemoService):
    """HTTP service for deployment configs, deployments, volumes, and controller status."""

    name: ClassVar[str] = "deployments"
    dependencies: ClassVar[list[str]] = ["entities", "auth"]

    def __init__(self) -> None:
        self._executor_registry: ExecutorRegistry | None = None

    @property
    def executor_registry(self) -> ExecutorRegistry:
        if self._executor_registry is None:
            self._executor_registry = ExecutorRegistry.empty()
        return self._executor_registry

    @classmethod
    def get_authz_contribution(cls) -> AuthzContribution:
        """Authorization policy for deployments plugin routes."""
        base = f"/apis/{cls.name}/v2/workspaces/{{workspace}}"
        permissions: dict[str, str] = {}
        endpoints: dict[str, dict[str, AuthzEndpointMethod]] = {}

        for resource, path_segment in (
            ("deployment-configs", "deployment-configs"),
            ("deployments", "deployments"),
            ("volumes", "volumes"),
        ):
            create_perm = f"{cls.name}.{resource}.create"
            list_perm = f"{cls.name}.{resource}.list"
            read_perm = f"{cls.name}.{resource}.read"
            delete_perm = f"{cls.name}.{resource}.delete"
            permissions.update(
                {
                    create_perm: f"Create {cls.name} {resource}",
                    list_perm: f"List {cls.name} {resource}",
                    read_perm: f"Read {cls.name} {resource}",
                    delete_perm: f"Delete {cls.name} {resource}",
                }
            )
            endpoints[f"{base}/{path_segment}"] = {
                **_read_methods(list_perm),
                "post": _write_method(create_perm),
            }
            endpoints[f"{base}/{path_segment}/{{name}}"] = {
                "delete": _write_method(delete_perm),
                **_read_methods(read_perm),
            }

        deployment_status_perm = f"{cls.name}.deployments.status.update"
        volume_status_perm = f"{cls.name}.volumes.status.update"
        permissions[deployment_status_perm] = "Update deployment observed status (controller)"
        permissions[volume_status_perm] = "Update volume observed status (controller)"
        endpoints[f"{base}/deployments/{{name}}/status"] = {
            "put": _write_method(deployment_status_perm),
        }
        endpoints[f"{base}/volumes/{{name}}/status"] = {
            "put": _write_method(volume_status_perm),
        }

        return AuthzContribution(permissions=permissions, endpoints=endpoints)

    def get_routers(self) -> list[RouterSpec]:
        from nemo_deployments_plugin.api.v2 import (
            deployment_configs,
            deployments,
            status,
            volumes,
        )

        prefix = "/v2/workspaces/{workspace}"
        return [
            RouterSpec(
                deployment_configs.router,
                tag="Deployment Configs",
                description="Immutable deployment templates",
                prefix=prefix,
            ),
            RouterSpec(
                deployments.router,
                tag="Deployments",
                description="Deployment lifecycle",
                prefix=prefix,
            ),
            RouterSpec(
                volumes.router,
                tag="Volumes",
                description="Volume lifecycle",
                prefix=prefix,
            ),
            RouterSpec(
                status.router,
                tag="Deployment Status",
                description="Controller-only status projection",
                prefix=prefix,
            ),
        ]

    async def on_startup(self) -> None:
        config = DeploymentsConfig.get()
        sdk: AsyncNeMoPlatform = get_async_platform_sdk(as_service="deployments", internal=True)
        specs = [ExecutorSpec(name=e.name, backend=e.backend, config=e.config) for e in config.executors]
        if specs:
            self._executor_registry = ExecutorRegistry.from_config(
                sdk,
                specs,
                default_executor=config.default_executor,
            )
        else:
            self._executor_registry = ExecutorRegistry.empty()
            if config.default_executor:
                logger.warning(
                    "default_executor '%s' is configured but no executors are registered.",
                    config.default_executor,
                )
            logger.info("Deployments plugin started with zero registered executors.")

    async def on_shutdown(self) -> None:
        if self._executor_registry is not None:
            self._executor_registry.shutdown_all()
