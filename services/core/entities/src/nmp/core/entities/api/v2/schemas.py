# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared API Schemas for v2."""

from enum import StrEnum

from pydantic import BaseModel, Field


class WorkspaceSortField(StrEnum):
    """Fields available for sorting workspace results."""

    CREATED_AT_ASC = "created_at"
    CREATED_AT_DESC = "-created_at"
    UPDATED_AT_ASC = "updated_at"
    UPDATED_AT_DESC = "-updated_at"


class EntityDeleteResponse(BaseModel):
    """Response for successful delete operations."""

    message: str = Field(default="Resource deleted successfully")
    id: str = Field(..., description="ID of the deleted resource")
    deleted_count: int = Field(
        default=1,
        description="Number of items deleted",
    )
