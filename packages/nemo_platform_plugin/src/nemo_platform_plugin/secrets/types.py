# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Secrets service.

These types define the HTTP contract for secret CRUD, value access, and the
admin key-rotation endpoint. Both the server (FastAPI routes) and the client
(NemoClient endpoints) import from here — one source of truth, no
Stainless-generated duplicates.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import NotRequired, Self, TypedDict

from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator, model_validator

# Mirrors ``nmp.common.entities.constants.REGEX_WORD_CHARACTER_DOT_DASH``. Inlined
# rather than imported so this package stays free of an ``nmp_common`` dependency
# (matching the ``files.types`` boundary — plugin types own their own contract).
_NAME_REGEX = r"^[\w\-.]+$"
_NAME_RE: re.Pattern[str] = re.compile(_NAME_REGEX)

# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


class PlatformSecretResponse(BaseModel):
    """Response model for a platform secret."""

    name: str = Field(description="The name of the secret")
    workspace: str = Field(description="The workspace ID the secret belongs to")
    description: str | None = Field(default=None, description="An optional description of the secret")
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)


class PlatformSecretAccessResponse(BaseModel):
    """Response model for accessing a platform secret's value."""

    name: str = Field(description="The name of the secret")
    workspace: str = Field(description="The workspace ID the secret belongs to")
    value: str = Field(description="The payload of the secret")


class PlatformSecretAdminRotationResponse(BaseModel):
    """Response DTO for the admin key-rotation routine."""

    rotated_secrets: int
    success: bool


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------


class PlatformSecretCreateRequest(BaseModel):
    """Request body for creating a new platform secret."""

    # ``value`` is a ``SecretStr`` so it is masked in reprs/logs, but the
    # ``_serialize_value`` JSON serializer below emits the real plaintext on the
    # wire — without it, ``model_dump_json`` would send ``"**********"`` and the
    # server would store the mask instead of the secret. (Keep this as a comment,
    # not the class docstring, so it does not leak into the OpenAPI schema.)

    name: str = Field(
        description=(
            "The name of the secret to create. Allowed characters: letters (a-z, A-Z), "
            "digits (0-9), underscores, hyphens, and dots."
        ),
        examples=["hf-token", "wandb-api-key"],
    )
    description: str | None = Field(default=None, description="An optional description of the secret")
    value: SecretStr = Field(description="The payload of the secret")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                f"Invalid secret name '{v}'. Allowed characters: letters, digits, underscores, "
                "hyphens, and dots. Example: my-api-key"
            )
        return v

    @field_serializer("value", when_used="json")
    def _serialize_value(self, value: SecretStr) -> str:
        return value.get_secret_value()

    @model_validator(mode="after")
    def _validate_value(self) -> Self:
        if not self.value.get_secret_value():
            raise ValueError("Secret value cannot be empty")
        return self


class PlatformSecretUpdateRequest(BaseModel):
    """Request body for updating a platform secret's metadata."""

    description: str | None = Field(default=None, description="An optional description of the secret")
    value: SecretStr | None = Field(default=None, description="The new secret value")

    @field_serializer("value", when_used="json")
    def _serialize_value(self, value: SecretStr | None) -> str | None:
        return value.get_secret_value() if value is not None else None

    @model_validator(mode="after")
    def _validate_value(self) -> Self:
        if self.value is not None and not self.value.get_secret_value():
            raise ValueError("Secret value cannot be empty")
        return self


# ---------------------------------------------------------------------------
# Query parameter types
# ---------------------------------------------------------------------------


class ListSecretsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
