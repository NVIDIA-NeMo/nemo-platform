# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployments plugin API schema definitions — request bodies and filters."""

from __future__ import annotations

from typing import Any

from nemo_deployments_plugin.entities import (
    AccessMode,
    ConfigFile,
    Container,
    Deployment,
    DeploymentBackendConfig,
    DeploymentConfig,
    DeploymentStatus,
    DesiredState,
    DriftRecoveryPolicy,
    Prerequisite,
    RestartPolicy,
    Volume,
    VolumeBackendConfig,
    VolumeMount,
    VolumeStatus,
)
from nemo_platform_plugin.schema import NemoFilter, NemoListResponse
from pydantic import BaseModel, Field


class CreateDeploymentConfigRequest(BaseModel):
    name: str
    containers: list[Container] = Field(default_factory=list)
    init_containers: list[Container] = Field(default_factory=list)
    volume_mounts: list[VolumeMount] = Field(default_factory=list)
    config_files: list[ConfigFile] = Field(default_factory=list)
    restart_policy: RestartPolicy = "Always"
    backoff_limit: int = 6
    prerequisites: list[Prerequisite] = Field(default_factory=list)
    drift_recovery: DriftRecoveryPolicy | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    backend_config: DeploymentBackendConfig = Field(default_factory=DeploymentBackendConfig)


class CreateDeploymentRequest(BaseModel):
    name: str
    deployment_config: str = Field(
        description="DeploymentConfig name in this workspace, or workspace/name for cross-workspace refs.",
    )
    desired_state: DesiredState = "READY"
    executor: str | None = None


class CreateVolumeRequest(BaseModel):
    name: str
    size: str = "1Gi"
    access_modes: list[AccessMode] = Field(default_factory=lambda: ["ReadWriteOnce"])
    backend_config: VolumeBackendConfig = Field(default_factory=VolumeBackendConfig)


class UpdateDeploymentStatusRequest(BaseModel):
    status: DeploymentStatus
    status_message: str = ""
    exit_code: int | None = None
    error_details: dict[str, Any] | None = None


class UpdateVolumeStatusRequest(BaseModel):
    status: VolumeStatus
    status_message: str = ""
    error_details: dict[str, Any] | None = None


class DeploymentConfigFilter(NemoFilter):
    restart_policy: RestartPolicy | None = None


class DeploymentFilter(NemoFilter):
    deployment_config: str | None = None
    desired_state: DesiredState | None = None
    executor: str | None = None
    status: DeploymentStatus | None = None


class VolumeFilter(NemoFilter):
    status: VolumeStatus | None = None


DeploymentConfigPage = NemoListResponse[DeploymentConfig]
DeploymentPage = NemoListResponse[Deployment]
VolumePage = NemoListResponse[Volume]
