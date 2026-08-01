# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccessKeyCreateRequest(BaseModel):
    """Request body for creating a Scoped Access Key."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional human-readable Scoped Access Key label. The token jti remains the stable identifier.",
    )
    expires_in_seconds: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Scoped Access Key lifetime in seconds. Omit to use "
            "auth.access_keys.default_expires_in_seconds. Send explicit null to request "
            "a non-time-delimited key, which requires auth.access_keys.max_expires_in_seconds "
            "to be disabled."
        ),
    )


class AccessKeyMetadataResponse(BaseModel):
    """Metadata for a Scoped Access Key."""

    jti: str = Field(description="Stable JWT ID for this Scoped Access Key.")
    name: str | None = Field(default=None, description="Optional human-readable Scoped Access Key label.")
    principal: str = Field(description="Principal ID stamped into the token.")
    created_at: datetime
    expires_at: datetime | None = None


class AccessKeyCreateResponse(AccessKeyMetadataResponse):
    """Create response. The token value is returned only once."""

    token: str
    token_type: Literal["Bearer"]


class AccessKeyListResponse(BaseModel):
    """List response for Scoped Access Key metadata."""

    data: list[AccessKeyMetadataResponse]


class AccessKeyAuthenticateResponse(BaseModel):
    """Successful Scoped Access Key authentication response for gateway callouts."""

    jti: str
    principal: str
    email: str | None = None
    groups: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class AccessKeyNotImplementedErrorResponse(BaseModel):
    """Response returned by unsupported Scoped Access Key lifecycle endpoints."""

    detail: str


class JsonWebKey(BaseModel):
    """JSON Web Key object."""

    model_config = ConfigDict(extra="allow")
