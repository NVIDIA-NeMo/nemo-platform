# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Volume mount readiness gating before deployment create."""

from __future__ import annotations

from dataclasses import dataclass

from nemo_deployments_plugin.entities import DeploymentConfig, Volume


@dataclass(frozen=True)
class VolumeMountResult:
    ready: bool
    reason: str = ""
    blocking_volume: str | None = None


def collect_volume_mount_names(config: DeploymentConfig) -> set[str]:
    """Collect unique volume names referenced by pod- and container-level mounts."""
    names = {mount.name for mount in config.volume_mounts}
    for container in (*config.containers, *config.init_containers):
        names.update(mount.name for mount in container.volume_mounts)
    return names


def volume_mounts_ready(
    config: DeploymentConfig,
    workspace: str,
    volumes_by_name: dict[tuple[str, str], Volume],
) -> VolumeMountResult:
    """Return whether all mounted volumes exist and are BOUND."""
    for mount_name in sorted(collect_volume_mount_names(config)):
        volume = volumes_by_name.get((workspace, mount_name))
        if volume is None:
            return VolumeMountResult(
                ready=False,
                reason=f"Waiting for volume '{mount_name}'",
                blocking_volume=mount_name,
            )
        if volume.status == "FAILED":
            return VolumeMountResult(
                ready=False,
                reason=f"Volume '{mount_name}' failed",
                blocking_volume=mount_name,
            )
        if volume.status != "BOUND":
            return VolumeMountResult(
                ready=False,
                reason=f"Waiting for volume '{mount_name}' to reach BOUND (currently {volume.status})",
                blocking_volume=mount_name,
            )
    return VolumeMountResult(ready=True)
