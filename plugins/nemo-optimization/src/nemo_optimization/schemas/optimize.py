# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical optimize study spec."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OptimizeSpec(BaseModel):
    """Spec for an Agents optimize study (``nemo agents optimize``)."""

    optimize_config: str = Field(description="Absolute path to the Fabric-native optimization YAML file.")
    workspace: str = Field(
        default="default",
        description="Workspace used to fetch a platform agent and for VirtualModel preflight.",
    )
    agent: str | None = Field(
        default=None,
        description="Optional platform agent reference ('name' or 'workspace/name'). "
        "When omitted, optimize_config must include an inline Fabric agent package.",
    )
