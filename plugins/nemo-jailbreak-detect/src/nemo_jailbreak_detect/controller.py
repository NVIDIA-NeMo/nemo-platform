# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployment controller for self-hosted jailbreak-detection model servers.

Owns the deployment lifecycle. The service writes desired state into a
:class:`JailbreakDetectorDeployment` entity; this controller reconciles it
against a backend (Docker now, Jobs/k8s later) on a fixed interval:

    pending  → start backend          → starting
    starting → readiness probe passes → running (+ endpoint_url)
    running  → health check           → running | failed
    stopping → stop backend           → delete entity
    failed   → leave for operator / next manual edit
"""

from __future__ import annotations

import logging
from typing import ClassVar, cast

from nemo_jailbreak_detect.deployment.backend import DeploymentSpec, get_backend
from nemo_jailbreak_detect.entities import JailbreakDetectorDeployment
from nemo_platform_plugin.controller import NemoController
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError

logger = logging.getLogger(__name__)


class JailbreakDetectController(NemoController):
    """Reconciles :class:`JailbreakDetectorDeployment` entities."""

    name: ClassVar[str] = "jailbreak-detect"
    dependencies: ClassVar[list[str]] = ["entities"]

    def __init__(self) -> None:
        # __init__ sets None sentinels only — no platform calls here.
        self._entities: NemoEntitiesClient | None = None
        self._interval_seconds: float = 10.0
        self._model_cache_dir: str = "/opt/nemo/jailbreak-detect/cache"
        self._request_timeout: float = 30.0

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    @property
    def entities(self) -> NemoEntitiesClient:
        if self._entities is None:
            raise RuntimeError("entities accessed before on_startup()")
        return self._entities

    async def on_startup(self) -> None:
        from nemo_jailbreak_detect.config import JailbreakDetectConfig
        from nemo_platform.resources.entities import AsyncEntitiesResource
        from nmp.common.sdk_factory import get_async_platform_sdk

        config = JailbreakDetectConfig.get()
        self._interval_seconds = float(config.controller_interval_seconds)
        self._model_cache_dir = config.model_cache_dir
        self._request_timeout = config.request_timeout_seconds

        sdk = get_async_platform_sdk(as_service="jailbreak-detect", internal=True)
        self._entities = NemoEntitiesClient(AsyncEntitiesResource(sdk))
        logger.info("JailbreakDetectController started (interval=%.1fs)", self._interval_seconds)

    async def on_shutdown(self) -> None:
        logger.info("JailbreakDetectController shutting down.")

    async def list_objects(self) -> list:
        try:
            result = await self.entities.list(JailbreakDetectorDeployment, workspace="-")
            return result.data
        except Exception:
            logger.exception("Failed to list jailbreak-detect deployments")
            return []

    async def reconcile_one(self, obj: object) -> None:
        deployment = cast(JailbreakDetectorDeployment, obj)
        try:
            await self._reconcile_one(deployment)
        except NemoEntityConflictError:
            logger.debug("Optimistic lock conflict on '%s' — retry next cycle.", deployment.name)
        except Exception as exc:
            logger.exception("Reconcile failed for '%s'", deployment.name)
            await self._mark_failed(deployment, str(exc))

    async def _reconcile_one(self, deployment: JailbreakDetectorDeployment) -> None:
        if deployment.status == "pending":
            await self._start(deployment)
        elif deployment.status == "starting":
            await self._await_ready(deployment)
        elif deployment.status == "running":
            await self._verify_running(deployment)
        elif deployment.status == "stopping":
            await self._stop(deployment)
        # "failed"/"stopped" are terminal until an operator edits the entity.

    def _spec(self, deployment: JailbreakDetectorDeployment) -> DeploymentSpec:
        config = _require(deployment)
        return DeploymentSpec(
            name=deployment.name,
            image=config["image"],
            device=config["device"],
            port=config["port"],
            model_cache_dir=self._model_cache_dir,
        )

    async def _start(self, deployment: JailbreakDetectorDeployment) -> None:
        backend = get_backend(deployment.backend)
        result = await backend.ensure_started(self._spec(deployment))
        deployment.handle = result.handle
        deployment.endpoint_url = result.endpoint_url
        deployment.status = "starting"
        deployment.last_error = None
        await self.entities.update(deployment)
        logger.info("Started deployment '%s' → %s", deployment.name, result.endpoint_url)

    async def _await_ready(self, deployment: JailbreakDetectorDeployment) -> None:
        backend = get_backend(deployment.backend)
        if deployment.endpoint_url and await backend.is_ready(deployment.endpoint_url, self._request_timeout):
            deployment.status = "running"
            deployment.last_error = None
            await self.entities.update(deployment)
            logger.info("Deployment '%s' is ready.", deployment.name)

    async def _verify_running(self, deployment: JailbreakDetectorDeployment) -> None:
        backend = get_backend(deployment.backend)
        if deployment.endpoint_url and not await backend.is_ready(deployment.endpoint_url, self._request_timeout):
            await self._mark_failed(deployment, "health check failed")

    async def _stop(self, deployment: JailbreakDetectorDeployment) -> None:
        backend = get_backend(deployment.backend)
        if deployment.handle:
            await backend.stop(deployment.handle)
        await self.entities.delete(JailbreakDetectorDeployment, name=deployment.name, workspace=deployment.workspace)
        logger.info("Stopped and removed deployment '%s'.", deployment.name)

    async def _mark_failed(self, deployment: JailbreakDetectorDeployment, reason: str) -> None:
        try:
            deployment.status = "failed"
            deployment.last_error = reason
            await self.entities.update(deployment)
        except NemoEntityConflictError:
            logger.debug("Could not mark '%s' failed (conflict); retry next cycle.", deployment.name)


def _require(deployment: JailbreakDetectorDeployment) -> dict:
    """Resolve the effective spec fields, falling back to plugin config defaults."""
    from nemo_jailbreak_detect.config import JailbreakDetectConfig

    config = JailbreakDetectConfig.get()
    return {
        "image": deployment.image or config.server_image,
        "device": deployment.device or config.default_device,
        "port": deployment.port or config.default_port,
    }
