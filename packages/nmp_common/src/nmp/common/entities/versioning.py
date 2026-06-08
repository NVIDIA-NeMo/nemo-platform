# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared types for opt-in entity versioning."""

from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class VersionedEntityMeta(TypedDict):
    """Fields expected in the `data` blob of a versioned parent entity.

    Entity types that opt into versioning must keep these keys in sync.
    version_count never decrements (versions are append-only).
    """

    version_count: NotRequired[int]
    current_version_name: NotRequired[str]


class EntityVersionMeta(TypedDict):
    """Minimum fields expected in the `data` blob of a version child entity."""

    version_number: NotRequired[int]
    change_note: NotRequired[str | None]


class EntityVersionRef(BaseModel):
    """A typed reference from one entity to a specific version of another.

    Pinned (version_name set): resolves to exactly that child entity — use for
    evaluations and any context where reproducibility across reruns matters.

    Floating (version_name=None): resolves to whatever current_version_name
    the parent carries at the time of resolution — use for agent/pipeline
    configs where "latest" is the desired behavior.
    """

    entity_id: str = Field(..., description="Stable ID of the parent (versioned) entity.")
    version_name: str | None = Field(
        default=None,
        description=(
            "Name of the specific version entity to pin to (e.g. 'my-prompt-v3'). "
            "None means resolve to the parent's current_version_name at runtime."
        ),
    )
