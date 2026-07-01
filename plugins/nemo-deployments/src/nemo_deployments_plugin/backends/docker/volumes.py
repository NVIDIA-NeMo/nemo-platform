# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker volume lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nemo_deployments_plugin.backends.base import VolumeStatusUpdate
from nemo_deployments_plugin.backends.docker.labels import docker_volume_name, volume_identity_labels

import docker

logger = logging.getLogger(__name__)


async def create_volume(
    client: docker.DockerClient,
    *,
    workspace: str,
    name: str,
    driver: str = "local",
) -> VolumeStatusUpdate:
    vol_name = docker_volume_name(workspace, name)
    labels = volume_identity_labels(workspace, name)

    def _create() -> Any:
        from docker.errors import NotFound

        try:
            existing = client.volumes.get(vol_name)
            existing.reload()
            return existing
        except NotFound:
            return client.volumes.create(name=vol_name, driver=driver, labels=labels)

    try:
        await asyncio.to_thread(_create)
        return VolumeStatusUpdate(status="BOUND", status_message=f"Volume {vol_name} is bound")
    except Exception as exc:
        logger.exception("Failed to create volume %s", vol_name)
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to create volume: {exc}")


async def read_volume_status(client: docker.DockerClient, *, workspace: str, name: str) -> VolumeStatusUpdate:
    vol_name = docker_volume_name(workspace, name)

    def _get() -> Any:
        from docker.errors import NotFound

        try:
            return client.volumes.get(vol_name)
        except NotFound:
            raise

    try:
        volume = await asyncio.to_thread(_get)
        volume.reload()
        return VolumeStatusUpdate(status="BOUND", status_message=f"Volume {volume.name} is bound")
    except Exception as exc:
        from docker.errors import NotFound

        if isinstance(exc, NotFound):
            return VolumeStatusUpdate(status="FAILED", status_message=f"Volume {vol_name} not found")
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to read volume: {exc}")


async def delete_volume(client: docker.DockerClient, *, workspace: str, name: str) -> VolumeStatusUpdate:
    vol_name = docker_volume_name(workspace, name)

    def _remove() -> None:
        from docker.errors import NotFound

        try:
            volume = client.volumes.get(vol_name)
            volume.remove(force=True)
        except NotFound:
            return

    try:
        await asyncio.to_thread(_remove)
        return VolumeStatusUpdate(status="RELEASED", status_message=f"Volume {vol_name} released")
    except Exception as exc:
        return VolumeStatusUpdate(status="FAILED", status_message=f"Failed to delete volume: {exc}")
