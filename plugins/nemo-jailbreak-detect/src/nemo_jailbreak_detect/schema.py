# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""API request/response schemas for the jailbreak-detection service.

Entity objects are returned directly as responses (see ``service.py``); these
models cover request bodies and the inline ``classify`` contract.
"""

from __future__ import annotations

from typing import Literal

from nemo_jailbreak_detect.entities import JailbreakDetectorDeployment
from nemo_platform_plugin.schema import NemoFilter, NemoListResponse
from pydantic import BaseModel


class CreateDeploymentRequest(BaseModel):
    name: str
    backend: Literal["docker", "jobs"] | None = None
    image: str | None = None
    device: str | None = None
    port: int | None = None


class DeploymentFilter(NemoFilter):
    status: str | None = None
    backend: str | None = None


DeploymentPage = NemoListResponse[JailbreakDetectorDeployment]


class ClassifyRequest(BaseModel):
    """NIM-compatible classify request."""

    input: str


class ClassifyResponse(BaseModel):
    jailbreak: bool
    score: float
