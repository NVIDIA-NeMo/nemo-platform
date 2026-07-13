# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stable deployments-plugin entity names for a model deployment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityNames:
    """Names of the substrate entities managed for one model deployment."""

    volume: str
    puller: str
    server: str


def entity_names(name: str) -> EntityNames:
    """Return names relative to the ModelDeployment name."""
    return EntityNames(volume=f"{name}-weights", puller=f"{name}-puller", server=f"{name}-server")
