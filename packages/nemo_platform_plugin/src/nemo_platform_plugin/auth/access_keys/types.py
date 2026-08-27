# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

AccessKeyStatus = Literal["ACTIVE", "EXPIRED", "REVOKED", "SUSPENDED"]
AccessKeyReversibleStatus = Literal["ACTIVE", "EXPIRED", "SUSPENDED"]
AccessKeyEntityType = Literal["USER", "SERVICE_ACCOUNT"]


class AccessKeyListQueryParams(TypedDict, total=False):
    """Pagination parameters for Scoped Access Key listing."""

    page: int
    page_size: int


class AccessKeyCreateRequest(BaseModel):
    """Request body for creating a Scoped Access Key."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        json_schema_extra={"nullable": True},
        description="Optional human-readable Scoped Access Key label. The token jti remains the stable identifier.",
    )
    description: str | None = Field(
        default=None,
        max_length=1024,
        json_schema_extra={"nullable": True},
        description="Optional human-readable description of the Scoped Access Key.",
    )
    expires_in_seconds: int | None = Field(
        default=None,
        ge=1,
        json_schema_extra={"nullable": True},
        description=(
            "Scoped Access Key lifetime in seconds. Omit to use "
            "auth.access_keys.default_expires_in_seconds. Send explicit null to request "
            "a non-time-delimited key, which requires auth.access_keys.max_expires_in_seconds "
            "to be disabled."
        ),
    )
    service_account_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._+/-]*$",
        json_schema_extra={"nullable": True},
        description=(
            "Optional non-human service account to bind the key to. Service-bound keys can only be "
            "created by a PlatformAdmin and authenticate as service-account:<id>."
        ),
    )


class AccessKeyMetadataResponse(BaseModel):
    """Metadata for a Scoped Access Key."""

    jti: str = Field(description="Stable JWT ID for this Scoped Access Key.")
    name: str | None = Field(
        default=None,
        json_schema_extra={"nullable": True},
        description="Optional human-readable Scoped Access Key label.",
    )
    description: str | None = Field(
        default=None,
        json_schema_extra={"nullable": True},
        description="Human-readable description of the Scoped Access Key.",
    )
    principal: str = Field(description="Principal ID stamped into the token.")
    entity_type: AccessKeyEntityType = Field(
        default="USER",
        description="Whether the key is bound to a user or a non-human service account.",
    )
    status: AccessKeyStatus
    issuer: str = Field(description="Issuer stamped into the Scoped Access Key JWT.")
    audiences: list[str] = Field(
        description="Audiences accepted for the Scoped Access Key JWT.",
        json_schema_extra={"uniqueItems": True},
    )
    created_at: datetime
    expires_at: datetime | None = Field(default=None, json_schema_extra={"nullable": True})


class AccessKeyCreateResponse(AccessKeyMetadataResponse):
    """Create response. The token value is returned only once."""

    token: str
    token_type: Literal["Bearer"]


class AccessKeyListResponse(BaseModel):
    """List response for Scoped Access Key metadata."""

    data: list[AccessKeyMetadataResponse]
    has_more: bool = Field(
        default=False,
        description="True when another page of keys is available.",
    )


class AccessKeyRevokeResponse(BaseModel):
    """Response returned after a Scoped Access Key revoke request."""

    jti: str = Field(description="Stable JWT ID for this Scoped Access Key.")
    revoked: bool = Field(description="True when this request newly recorded the key's revocation.")


class AccessKeyStatusChangeResponse(BaseModel):
    """Response returned after a reversible Scoped Access Key status change."""

    jti: str = Field(description="Stable JWT ID for this Scoped Access Key.")
    status: AccessKeyReversibleStatus = Field(
        description="Resulting effective status of the key, including expiration."
    )
    changed: bool = Field(description="True when this request changed the key's persistent status.")


class AccessKeyNotImplementedErrorResponse(BaseModel):
    """Response returned by unsupported Scoped Access Key lifecycle endpoints."""

    detail: str


class JsonWebKey(BaseModel):
    """JSON Web Key object."""

    model_config = ConfigDict(extra="allow")
