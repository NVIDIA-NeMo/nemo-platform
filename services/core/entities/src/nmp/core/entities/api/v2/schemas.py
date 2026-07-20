# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared API Schemas for v2."""

from pydantic import BaseModel, Field


class EntityDeleteResponse(BaseModel):
    """Response for successful delete operations."""

    message: str = Field(default="Resource deleted successfully")
    id: str = Field(..., description="ID of the deleted resource")
    deleted_count: int = Field(
        default=1,
        description="Number of items deleted",
    )
