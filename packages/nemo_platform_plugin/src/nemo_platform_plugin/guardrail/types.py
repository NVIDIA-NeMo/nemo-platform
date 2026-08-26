# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request/response types for the Guardrails service.

Single source of truth for the HTTP contract. Replaces the Stainless-generated
``nemo_platform.types.guardrail`` module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from nemo_platform_plugin.schema import Page
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


class GuardrailConfig(BaseModel):
    """A guardrail configuration entity."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    workspace: str
    project: str | None = None
    description: str | None = None
    data: dict[str, Any] = Field(default_factory=dict, description="Guardrail configuration data")
    id: str
    created_at: datetime
    created_by: str | None = None
    updated_at: datetime
    updated_by: str | None = None


GuardrailConfigPage = Page[GuardrailConfig]


class GuardrailCheckResponse(BaseModel):
    """Response from a guardrail check request."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------


class CreateGuardrailConfigRequest(BaseModel):
    """Input schema for creating a guardrail config."""

    name: str
    description: str | None = None
    data: dict[str, Any] = Field(default_factory=dict, description="Guardrail configuration data")


class UpdateGuardrailConfigRequest(BaseModel):
    """Input schema for updating a guardrail config."""

    description: str | None = None
    data: dict[str, Any] | None = None


class GuardrailCheckRequest(BaseModel):
    """Guardrail check request body."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Query parameter types
# ---------------------------------------------------------------------------


class ListGuardrailConfigsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]
    project: NotRequired[str]
