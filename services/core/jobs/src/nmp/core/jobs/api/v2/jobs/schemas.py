# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schemas for the v2 Jobs Service.

This module contains:
- View models (PlatformJob, PlatformJobStepWithContext)
- Request/response schemas
- Filter schemas
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from nmp.common.auth import AuthContext
from nmp.common.entities import (
    DatetimeFilter,
    Filter,
    StringFilter,
    Value,
    get_random_id,
)
from nmp.common.jobs.schemas import PlatformJobResultResponse, PlatformJobStatus
from nmp.core.jobs.entities import PlatformJobSpec, PlatformJobStepSpec, PlatformJobTask
from pydantic import BaseModel, Field

# =============================================================================
# Utilities
# =============================================================================


def get_model_id(prefix: str) -> str:
    """Generate a random ID with the given prefix.

    Uses lowercase characters for compatibility with all platform identifiers.
    """
    # `get_random_id` includes uppercase characters, which won't
    # work with all platform identifiers.
    return get_random_id(prefix).lower()


# =============================================================================
# Sort Fields
# =============================================================================


class PlatformJobLogSortField(str, Enum):
    TIMESTAMP_ASC = "timestamp"
    TIMESTAMP_DESC = "-timestamp"

    def get_field_name(self) -> str:
        return self.value.lstrip("-")

    def get_sort_direction(self) -> str:
        return "desc" if self.value.startswith("-") else "asc"


class PlatformJobSortField(str, Enum):
    CREATED_AT_ASC = "created_at"
    CREATED_AT_DESC = "-created_at"
    UPDATED_AT_ASC = "updated_at"
    UPDATED_AT_DESC = "-updated_at"

    def get_field_name(self) -> str:
        return self.value.lstrip("-")

    def get_sort_direction(self) -> str:
        return "desc" if self.value.startswith("-") else "asc"


class PlatformJobAttemptSortField(str, Enum):
    SEQ_ASC = "seq"
    SEQ_DESC = "-seq"

    def get_field_name(self) -> str:
        return self.value.lstrip("-")

    def get_sort_direction(self) -> str:
        return "desc" if self.value.startswith("-") else "asc"


# =============================================================================
# View Models (composite models for API responses)
# =============================================================================

# Import entities here to avoid circular imports at module level
# These are used in view models and will be imported when needed


class PlatformJobResponse(BaseModel):
    """Response model for a platform job."""

    id: str
    attempt_id: str
    name: str
    workspace: str = Field(..., description="Workspace identifier")
    project: Optional[str] = Field(default=None, description="Project URN")
    description: str | None = None
    source: str
    spec: Dict[str, Any] = Field(default_factory=dict, description="Job Spec")
    platform_spec: PlatformJobSpec
    fileset: str = Field(..., description="Fileset ID for storing job artifacts")
    status: PlatformJobStatus
    status_details: Dict[str, Any] = Field(default_factory=dict, description="Details about the job status")
    error_details: Dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ownership: Optional[Dict[str, Any]] = None
    custom_fields: Optional[Dict[str, Any]] = Field(default=None, description="Custom Fields")


class PlatformJobStepWithContext(BaseModel):
    """Step with additional context from parent job/attempt."""

    id: str
    job: str
    attempt_id: str
    fileset: str
    workspace: str
    name: str
    step_spec: PlatformJobStepSpec | None = None
    status: PlatformJobStatus = PlatformJobStatus.CREATED
    status_details: Dict[str, Any] | None = None
    error_details: Dict[str, Any] | None = None
    auth_context: Optional[AuthContext] = Field(default=None, description="Auth context for task execution")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Request Schemas
# =============================================================================


class CreatePlatformJobRequest(BaseModel):
    """Request model for creating a new platform job."""

    name: Optional[str] = None
    description: Optional[str] = None
    project: Optional[str] = None
    spec: dict
    platform_spec: PlatformJobSpec
    source: str
    ownership: Optional[dict] = None
    custom_fields: Optional[dict] = None


class PlatformJobTaskUpdate(BaseModel):
    """Request model for updating a platform job task."""

    status: PlatformJobStatus = PlatformJobStatus.PENDING
    status_details: Dict[str, Any] | None = None
    error_details: Dict[str, Any] | None = None
    error_stack: str | None = None


class PlatformJobStatusUpdateRequest(BaseModel):
    """Request model for updating job status."""

    status: PlatformJobStatus = Field(..., description="The new status to set for the job.")
    status_details: Dict[str, Any] | None = Field(
        default_factory=dict, description="Optional status details related to the status update."
    )
    error_details: Dict[str, Any] | None = Field(
        default_factory=dict, description="Optional error details related to the status update."
    )


PlatformJobStatusDetailsUpdateRequest = Dict[str, Any]


# =============================================================================
# Response Schemas
# =============================================================================


class PlatformJobListResultResponse(Value):
    """Response model for listing job results."""

    data: List[PlatformJobResultResponse]


class PlatformJobListTaskResponse(Value):
    """Response model for listing job tasks."""

    data: List[PlatformJobTask]


# =============================================================================
# Filter Schemas
# =============================================================================


class PlatformJobsListFilter(Filter):
    """Filter options for listing platform jobs."""

    workspace: Optional[str] = Field(None, description="Workspace of the job.")
    project: Optional[str] = Field(None, description="Project of the job.")
    name: StringFilter | str | None = Field(None, description="Name of the job.")
    created_at: Optional[DatetimeFilter] = Field(None, description="Jobs created at 'gte' datetime or 'lte' datetime.")
    updated_at: Optional[DatetimeFilter] = Field(None, description="Jobs updated at 'gte' datetime or 'lte' datetime.")
    status: Optional[PlatformJobStatus | list[PlatformJobStatus]] = Field(None, description="The current status.")
    source: StringFilter | str | None = Field(None, description="The source of the job.")


class PlatformJobAttemptsListFilter(Filter):
    """Filter options for listing platform job attempts."""

    status: Optional[PlatformJobStatus] = Field(None, description="The current status.")


class PlatformJobStepsListFilter(Filter):
    """Filter options for listing platform job steps."""

    # job/source kept as str pending AIRCORE-388 (read as scalars by the in-memory dispatcher)
    job: Optional[str] = Field(None, description="The ID of the job to filter steps by.")
    status: Optional[List[PlatformJobStatus]] = Field(None, description="The list of statuses to filter steps by.")
    source: Optional[str] = Field(None, description="The source of the job steps.")
