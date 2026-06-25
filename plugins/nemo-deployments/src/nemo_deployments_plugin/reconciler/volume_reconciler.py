# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Volume lifecycle reconciliation against DeploymentBackend."""

from __future__ import annotations

import logging

from nemo_deployments_plugin.backends.base import DeploymentBackend, VolumeStatusUpdate
from nemo_deployments_plugin.backends.registry import ExecutorNotFoundError, ExecutorRegistry
from nemo_deployments_plugin.entities import Volume
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError

logger = logging.getLogger(__name__)


class VolumeReconciler:
    """Reconciles Volume entities with backend volume resources."""

    def __init__(self, entities: NemoEntitiesClient, registry: ExecutorRegistry) -> None:
        self._entities = entities
        self._registry = registry

    async def reconcile_one(self, volume: Volume) -> None:
        try:
            backend = self._registry.resolve(None)
        except ExecutorNotFoundError as exc:
            await self._update_volume_status(
                volume,
                VolumeStatusUpdate(status="FAILED", status_message=f"No executor available: {exc}"),
            )
            return

        if volume.status == "PENDING":
            await self._reconcile_create(volume, backend)
        elif volume.status == "BOUND":
            await self._reconcile_read(volume, backend)

    async def _reconcile_create(self, volume: Volume, backend: DeploymentBackend) -> None:
        backend_config = volume.backend_config.model_dump(by_alias=True, exclude_none=True)
        try:
            update = await backend.create_volume(
                workspace=volume.workspace,
                name=volume.name,
                size=volume.size,
                access_modes=list(volume.access_modes),
                backend_config=backend_config,
            )
            await self._update_volume_status(volume, update)
            logger.info("Volume %s/%s created: %s", volume.workspace, volume.name, update.status)
        except NemoEntityConflictError:
            raise
        except Exception as exc:
            logger.exception("Failed to create volume %s/%s", volume.workspace, volume.name)
            await self._update_volume_status(
                volume,
                VolumeStatusUpdate(status="FAILED", status_message=f"Failed to create volume: {exc}"),
            )

    async def _reconcile_read(self, volume: Volume, backend: DeploymentBackend) -> None:
        try:
            update = await backend.read_volume_status(workspace=volume.workspace, name=volume.name)
            await self._update_volume_status(volume, update)
        except NemoEntityConflictError:
            raise
        except Exception as exc:
            logger.exception("Failed to read volume status %s/%s", volume.workspace, volume.name)
            await self._update_volume_status(
                volume,
                VolumeStatusUpdate(status="FAILED", status_message=f"Failed to read volume status: {exc}"),
            )

    async def _update_volume_status(self, volume: Volume, update: VolumeStatusUpdate) -> None:
        if (
            volume.status == update.status
            and volume.status_message == update.status_message
            and volume.error_details == update.error_details
        ):
            return
        volume.status = update.status
        volume.status_message = update.status_message
        volume.error_details = update.error_details
        await self._save(volume)

    async def _save(self, volume: Volume) -> None:
        try:
            await self._entities.update(volume)
        except NemoEntityConflictError:
            raise
