# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared deployment status and endpoint types (no entity imports)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DeploymentStatus = Literal[
    "PENDING",
    "STARTING",
    "READY",
    "SUCCEEDED",
    "FAILED",
    "LOST",
    "UNKNOWN",
    "DELETING",
]
VolumeStatus = Literal["PENDING", "BOUND", "DELETING", "RELEASED", "FAILED"]
DesiredState = Literal["READY", "STOPPED"]
RestartPolicy = Literal["Always", "OnFailure", "Never"]
AccessMode = Literal["ReadWriteOnce", "ReadOnlyMany", "ReadWriteMany"]
DriftRecoveryAction = Literal["recreate", "ignore"]
PrerequisiteCondition = Literal["ready", "succeeded"]

NON_TERMINAL_DEPLOYMENT_STATUSES: tuple[DeploymentStatus, ...] = (
    "PENDING",
    "STARTING",
    "READY",
    "LOST",
    "UNKNOWN",
    "DELETING",
)
NON_TERMINAL_VOLUME_STATUSES: tuple[VolumeStatus, ...] = ("PENDING", "BOUND", "DELETING")


class Endpoint(BaseModel):
    name: str
    url: str
    protocol: Literal["http", "https", "grpc", "tcp"] = "http"
