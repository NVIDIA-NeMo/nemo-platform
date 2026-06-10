# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""IAM schemas for API endpoints."""

from datetime import datetime
from typing import Optional

from nmp.common.entities.values import Filter, StringFilter
from pydantic import BaseModel, Field


class DateRangeFilter(BaseModel):
    """Filter for date ranges."""

    gte: Optional[datetime] = Field(None, description="Greater than or equal to this date")
    lte: Optional[datetime] = Field(None, description="Less than or equal to this date")


class RoleBindingInput(BaseModel):
    """Input schema for creating a role binding."""

    principal: str = Field(description="The principal identifier (email, user ID, or group ID)")
    workspace: Optional[str] = Field(
        default=None, description="The workspace this binding applies to. None for platform-level roles."
    )
    role: str = Field(description="The role name (e.g., 'Viewer', 'Editor', 'Admin')")


class RoleBindingUpdate(BaseModel):
    """Input schema for updating a role binding."""

    revoked_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the role was revoked (None if active)"
    )


class RoleBinding(BaseModel):
    """Role binding response model."""

    id: str
    name: str
    principal: str
    workspace: Optional[str]
    role: str
    granted_by: str
    granted_at: datetime
    revoked_at: Optional[datetime]


class RoleBindingFilter(Filter):
    """Filter for role bindings."""

    principal: StringFilter | str | None = Field(None, description="Filter by principal ID")
    workspace: Optional[str] = Field(None, description="Filter by workspace")
    role: StringFilter | str | None = Field(None, description="Filter by role")
    granted_by: StringFilter | str | None = Field(None, description="Filter by who granted the role")
    is_active: Optional[bool] = Field(default=None, description="Filter for active (True) or revoked (False) bindings")
    granted_at: Optional[DateRangeFilter] = Field(None, description="Filter by granted date range")
    revoked_at: Optional[DateRangeFilter] = Field(None, description="Filter by revoked date range")


class WorkspaceMemberInput(BaseModel):
    """Input schema for adding a workspace member."""

    principal: str = Field(description="The principal identifier (email, user ID, or group ID)")
    roles: list[str] = Field(default=["Editor"], description="List of roles to grant to the principal")


class WorkspaceMemberUpdate(BaseModel):
    """Input schema for updating a workspace member."""

    roles: list[str] = Field(description="Updated list of roles for the principal")


class WorkspaceMember(BaseModel):
    """Workspace member response model."""

    principal: str
    roles: list[str]
