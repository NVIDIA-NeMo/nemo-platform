# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prompt API Schemas for v2."""

import re
from datetime import datetime

from nmp.common.entities.constants import NAME_PATTERN, NAME_PATTERN_DESCRIPTION
from pydantic import BaseModel, ConfigDict, Field

VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def extract_variables(template: str) -> list[str]:
    """Extract unique {{variable}} placeholders from a prompt template, preserving order."""
    return list(dict.fromkeys(VARIABLE_PATTERN.findall(template)))


class PromptModelParams(BaseModel):
    temperature: float | None = Field(
        default=None, ge=0, le=2, description="Sampling temperature (0–2). Higher values produce more random output."
    )
    max_tokens: int | None = Field(default=None, description="Maximum number of tokens to generate.")
    top_p: float | None = Field(default=None, ge=0, le=1, description="Nucleus sampling probability mass (0–1).")

    model_config = ConfigDict(extra="forbid")


class PromptCreate(BaseModel):
    name: str | None = Field(
        default=None,
        description=f"Prompt name (optional — auto-generated if not provided). {NAME_PATTERN_DESCRIPTION}",
        pattern=NAME_PATTERN,
    )
    project: str | None = Field(default=None, description="Optional project to associate with this prompt.")
    description: str | None = Field(default=None, description="Human-readable description of the prompt's purpose.")
    tags: list[str] = Field(default=[], description="Free-form string tags for filtering and organisation.")
    template: str = Field(..., description="Prompt template text. Use {{variable}} for placeholders.")
    model_params: PromptModelParams | None = Field(
        default=None, description="Optional default model parameters for this prompt."
    )
    change_note: str | None = Field(default=None, description="Note describing the initial version.")

    model_config = ConfigDict(regex_engine="python-re", extra="forbid")


class PromptUpdate(BaseModel):
    description: str | None = Field(default=None, description="Updated description for the prompt.")
    tags: list[str] | None = Field(
        default=None, description="Replacement tag list. Pass an empty list to clear all tags."
    )
    project: str | None = Field(default=None, description="Updated project association. Pass null to disassociate.")

    model_config = ConfigDict(extra="forbid")


class PromptVersionCreate(BaseModel):
    template: str = Field(..., description="Prompt template text. Use {{variable}} for placeholders.")
    model_params: PromptModelParams | None = Field(
        default=None, description="Optional model parameter overrides for this version."
    )
    change_note: str | None = Field(default=None, description="What changed in this version.")

    model_config = ConfigDict(extra="forbid")


class PromptVersion(BaseModel):
    id: str = Field(..., description="Unique identifier for this prompt version entity.")
    name: str = Field(..., description="Entity name of this version (e.g. my-prompt-v2).")
    prompt_id: str = Field(..., description="ID of the parent prompt entity.")
    prompt_name: str = Field(..., description="Name of the parent prompt.")
    workspace: str = Field(..., description="Workspace that owns this prompt version.")
    version_number: int = Field(..., ge=1, description="Sequential version number, starting at 1.")
    template: str = Field(..., description="Full prompt template text for this version.")
    variables: list[str] = Field(
        ..., description="Ordered list of unique {{variable}} placeholders extracted from the template."
    )
    model_params: PromptModelParams | None = Field(
        default=None, description="Model parameter overrides for this version, if any."
    )
    change_note: str | None = Field(
        default=None, description="Human-readable note describing what changed in this version."
    )
    created_at: datetime = Field(..., description="ISO 8601 timestamp when this version was created.")
    created_by: str | None = Field(default=None, description="Identity that created this version.")
    updated_at: datetime = Field(..., description="ISO 8601 timestamp of the last update to this version entity.")

    model_config = ConfigDict(extra="forbid")


class Prompt(BaseModel):
    id: str = Field(..., description="Unique identifier for the prompt entity.")
    name: str = Field(..., description="Unique name of the prompt within its workspace.")
    workspace: str = Field(..., description="Workspace that owns this prompt.")
    project: str | None = Field(default=None, description="Project associated with this prompt, if any.")
    description: str | None = Field(default=None, description="Human-readable description of the prompt's purpose.")
    tags: list[str] = Field(default=[], description="Free-form string tags attached to this prompt.")
    version_count: int = Field(..., description="Total number of versions created for this prompt.")
    current_version: PromptVersion | None = Field(
        default=None, description="The most recently created version, or null if none exist."
    )
    created_at: datetime = Field(..., description="ISO 8601 timestamp when the prompt was created.")
    created_by: str | None = Field(default=None, description="Identity that created the prompt.")
    updated_at: datetime = Field(..., description="ISO 8601 timestamp of the last metadata update.")
    updated_by: str | None = Field(default=None, description="Identity that last updated the prompt metadata.")

    model_config = ConfigDict(extra="forbid")
