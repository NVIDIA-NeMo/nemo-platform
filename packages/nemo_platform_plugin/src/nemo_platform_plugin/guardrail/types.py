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


class RailStatus(BaseModel):
    """Status of an individual rail."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(description="Status of the individual rail: success, blocked, or unknown.")


class ActivatedRail(BaseModel):
    """A rail that ran during a check, as reported in the generation log."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    type: str = ""
    stop: bool = False


class GenerationLog(BaseModel):
    """Logging information about a guardrails generation."""

    model_config = ConfigDict(extra="allow")

    activated_rails: list[ActivatedRail] = Field(default_factory=list)


class GuardrailsDataOutput(BaseModel):
    """Guardrails-specific output attached to a check or chat response."""

    model_config = ConfigDict(extra="allow")

    llm_output: dict[str, Any] | None = None
    config_ids: list[str] | None = Field(default=None, description="Configuration ids that were used.")
    output_data: dict[str, Any] | None = None
    log: GenerationLog | None = Field(default=None, description="Populated when guardrails log options are requested.")


class GuardrailCheckResponse(BaseModel):
    """Response from a guardrail check request."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(description="Overall status: success if all rails passed, blocked if any failed.")
    rails_status: dict[str, RailStatus] = Field(
        default_factory=dict, description="Status of each rail, keyed by rail name."
    )
    guardrails_data: GuardrailsDataOutput | None = None


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
    """Guardrail check request body.

    Shaped like an OpenAI chat-completions request. ``extra="allow"`` passes
    through any additional sampling parameters the backend accepts.
    """

    model_config = ConfigDict(extra="allow")

    model: str = Field(description="The model the checked conversation targets.")
    messages: list[dict[str, Any]] = Field(description="The conversation to check, in OpenAI chat format.")
    guardrails: dict[str, Any] = Field(
        default_factory=dict,
        description="Guardrails options for the request, e.g. config_id, config, or options.",
    )
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None


# ---------------------------------------------------------------------------
# Query parameter types
# ---------------------------------------------------------------------------


class ListGuardrailConfigsQueryParams(TypedDict, total=False):
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]
    project: NotRequired[str]
