# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain entities for the Files service."""

from datetime import datetime
from typing import Any, ClassVar, Dict

from nemo_platform_plugin.files.dataset_profile import AnyFilesetProfile
from nemo_platform_plugin.files.types import FilesetPurpose as FilesetPurpose
from nmp.common.entities import constants
from nmp.common.entities.client import EntityBase
from nmp.common.files.metadata import FilesetMetadata
from nmp.core.files.app.backends.factory import StorageConfig
from pydantic import Field, model_validator


class Fileset(EntityBase):
    """Fileset domain model - represents a fileset entity."""

    __entity_type__: ClassVar[str] = "fileset"

    description: str | None = Field(
        default=None,
        description="The description of the fileset.",
        max_length=constants.MAX_LENGTH_255,
    )
    storage: StorageConfig = Field(description="The storage configuration for the fileset.")

    purpose: FilesetPurpose = Field(description="The purpose of the fileset.")
    metadata: FilesetMetadata = Field(
        default_factory=FilesetMetadata,
        description="Purpose-specific metadata for the fileset.",
    )

    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom fields for the fileset.")


class FilesetProfile(EntityBase):
    """The machine-computed dataset profile for one fileset.

    Its own entity rather than a field on ``Fileset``, for three reasons: the profile is
    server-managed (only the profiler task writes it, so it must not sit in a client-writable
    request body), it is large enough that loading it on every ``GET /filesets`` page would be
    waste, and its lifecycle is independent — a fileset can exist unprofiled, and re-profiling
    replaces the profile without touching the fileset.

    Parent-scoped: unique within (workspace, entity_type, parent=fileset), and since there is
    exactly one profile per fileset the name is always :data:`FILESET_PROFILE_ENTITY_NAME`.
    """

    __entity_type__: ClassVar[str] = "fileset_profile"

    fileset: str = Field(description="Parent fileset ID.")
    profile: AnyFilesetProfile = Field(description="The computed profile, discriminated by its `kind`.")

    @model_validator(mode="after")
    def set_parent_from_fileset(self) -> "FilesetProfile":
        """Scope uniqueness to the parent fileset, mirroring PlatformJobResult."""
        self._parent = self.fileset
        return self


# One profile per fileset, so the child entity's name is a constant rather than something to
# generate: the (workspace, type, parent, name) key is already unique on the parent alone.
FILESET_PROFILE_ENTITY_NAME = "profile"


class FileLock(EntityBase):
    """File lock entity for coordinating file writes across requests.

    Used to prevent multiple requests from caching the same file simultaneously.
    Locks are acquired before writing to cache and released after completion.
    Stale locks can be cleaned up by other requests based on acquired_at + TTL.
    """

    __entity_type__: ClassVar[str] = "file_lock"

    path: str = Field(description="The cache path being locked")
    acquired_at: datetime = Field(description="When the lock was acquired")
