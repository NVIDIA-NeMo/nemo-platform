# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker volume lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nemo_deployments_plugin.backends.base import VolumeStatusUpdate
from nemo_deployments_plugin.backends.labels import DEFAULT_RESOURCE_SCOPE, docker_volume_name, volume_identity_labels

import docker

logger = logging.getLogger(__name__)


async def create_volume(
    client: docker.DockerClient,
    *,
    workspace: str,
    name: str,
    driver: str = "local",
    init_chmod: str | None = None,
    init_image: str | None = None,
    resource_scope: str = DEFAULT_RESOURCE_SCOPE,
) -> VolumeStatusUpdate:
    vol_name = docker_volume_name(workspace, name)
    labels = volume_identity_labels(workspace, name, resource_scope=resource_scope)

    def _create() -> bool:
        """Create the volume if missing. Returns True if newly created."""
        from docker.errors import NotFound

        try:
            existing = client.volumes.get(vol_name)
            existing.reload()
            return False
        except NotFound:
            client.volumes.create(name=vol_name, driver=driver, labels=labels)
            return True

    def _init_permissions() -> None:
        # Docker named volumes are created root-owned (0755). Run an init
        # container to relax the mode so a non-root workload (e.g. the HF
        # weight-puller running as the image's default user) can write to it.
        # This is the docker analogue of a k8s fsGroup.
        #
        # chmod (rather than chown to the puller's uid) is deliberate: it keeps
        # this backend uid-agnostic — the puller runs as whatever user its image
        # declares, so there is no fixed uid to chown to. World-writable is an
        # acceptable posture for the single-node docker dev/test runtime.
        #
        # Invoke chmod directly (no `sh -c`) so a mode value is never shell-
        # interpolated, keeping this safe even if a future caller supplies an
        # untrusted mode.
        image = init_image or "docker.io/library/busybox"
        client.containers.run(
            image,
            entrypoint=["chmod"],
            command=[init_chmod, "/vol"],
            volumes={vol_name: {"bind": "/vol", "mode": "rw"}},
            remove=True,
            detach=False,
        )

    try:
        created = await asyncio.to_thread(_create)
        # Only initialize permissions on a fresh create; an already-initialized
        # volume does not need the init container re-run on every reconcile.
        if created and init_chmod:
            await asyncio.to_thread(_init_permissions)
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
