# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request and response schemas for filesets API."""

from typing import Annotated, Any, Dict, Optional

from nmp.common.api.common import Page
from nmp.common.entities import constants
from nmp.common.entities.values import DatetimeFilter, Filter, StringFilter, map_entity_field
from nmp.common.files.metadata import FilesetMetadata
from nmp.core.files.app.backends.base import StorageConfigType
from nmp.core.files.app.backends.factory import StorageConfig
from nmp.core.files.entities import Fileset, FilesetPurpose
from pydantic import BaseModel, Field


class FilesetOutput(BaseModel):
    """Response DTO for fileset operations."""

    id: str
    name: str
    workspace: str
    description: str
    purpose: FilesetPurpose
    storage: StorageConfig
    metadata: FilesetMetadata
    custom_fields: Dict[str, Any]
    project: str
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, entity: Fileset) -> "FilesetOutput":
        return cls(
            id=entity.id,
            name=entity.name,
            workspace=entity.workspace,
            description=entity.description or "",
            purpose=entity.purpose,
            storage=entity.storage,
            metadata=entity.metadata,
            custom_fields=entity.custom_fields,
            project=entity.project or "",
            created_at=entity.created_at.isoformat() if entity.created_at else "",
            updated_at=entity.updated_at.isoformat() if entity.updated_at else "",
        )


class FilesetFilter(Filter):
    """Filter schema for listing filesets."""

    name: StringFilter | str | None = Field(default=None, description="Filter by fileset name.")
    description: StringFilter | str | None = Field(default=None, description="Filter by fileset description.")
    purpose: Optional[FilesetPurpose] = Field(
        default=None,
        description="Filter by the purpose of the fileset (e.g., 'dataset', 'generic').",
    )
    storage_type: Annotated[Optional[StorageConfigType], map_entity_field("data.storage.type")] = Field(
        default=None,
        description="Filter by the storage backend type (e.g., 'local', 'ngc').",
    )
    created_at: Optional[DatetimeFilter] = Field(
        default=None,
        description="Filter by creation date. Supports '$gte' (on or after) and '$lte' (on or before) datetime filters.",
    )
    updated_at: Optional[DatetimeFilter] = Field(
        default=None,
        description="Filter by update date. Supports '$gte' (on or after) and '$lte' (on or before) datetime filters.",
    )


class CreateFilesetRequest(BaseModel):
    name: str = Field(
        description=f"The name of the fileset. {constants.REGEX_WORD_CHARACTER_DOT_DASH_DESCRIPTION}",
        max_length=constants.MAX_LENGTH_255,
        pattern=constants.REGEX_WORD_CHARACTER_DOT_DASH,
        examples=["training-data-v1", "llama-checkpoint"],
    )
    description: Optional[str] = Field(
        default=None,
        description="The description of the fileset.",
        max_length=constants.MAX_LENGTH_255,
    )
    project: Optional[str] = Field(
        default=None,
        description="The name of the project associated with this fileset.",
    )
    storage: StorageConfig | None = Field(
        default=None,
        description="The storage configuration for the fileset. If not provided, uses default storage.",
    )

    # TODO: Make this a required field eventually
    purpose: FilesetPurpose = Field(default=FilesetPurpose.GENERIC, description="The purpose of the fileset.")
    metadata: FilesetMetadata = Field(
        default_factory=FilesetMetadata,
        description="Purpose-specific metadata. Use the purpose as the key (e.g., {dataset: {...}}).",
    )
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="Custom fields for the fileset.")
    cache: bool = Field(
        default=False,
        description="Cache all files after creation. Only applies to external storage.",
    )


FilesetPage = Page[FilesetOutput]


class UpdateFilesetRequest(BaseModel):
    description: str | None = Field(
        default=None,
        description="The description of the fileset.",
        max_length=constants.MAX_LENGTH_255,
    )
    project: str | None = Field(
        default=None,
        description="The name of the project associated with this fileset.",
    )
    purpose: FilesetPurpose | None = Field(default=None, description="The purpose of the fileset.")
    metadata: FilesetMetadata | None = Field(
        default=None,
        description="Purpose-specific metadata. Use the purpose as the key (e.g., {dataset: {...}}).",
    )
    custom_fields: Dict[str, Any] | None = Field(default=None, description="Custom fields for the fileset.")
