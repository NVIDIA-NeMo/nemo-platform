# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights plugin API schemas — request bodies and filters.

Request bodies follow the ``CreateXRequest`` / ``UpdateXRequest`` convention.
Filters extend :class:`~nemo_platform_plugin.schema.NemoFilter` so typo'd filter
fields fail loudly with 422 rather than silently returning unfiltered results.
"""

from __future__ import annotations

from typing import Any

from nemo_platform_plugin.schema import NemoFilter, NemoListResponse
from pydantic import BaseModel, Field

from nemo_insights_plugin.entities import (
    AgentRegistration,
    CloudAgentType,
    Insight,
    InsightStatus,
    InsightTrace,
    InsightTraceRole,
)

# ---------------------------------------------------------------------------
# AgentRegistration
# ---------------------------------------------------------------------------


class CreateAgentRegistrationRequest(BaseModel):
    name: str = Field(description="Canonical agent name. Must match the agent_id span attribute emitted by the AUT.")
    description: str = Field(default="")
    repo_url: str = Field(default="")
    agent_description_path: str = Field(default="AGENT_DESCRIPTION.md")
    agent_description_content: str = Field(default="")
    eval_command: str = Field(default="")
    cloud_agent_type: CloudAgentType | None = Field(default=None)
    cloud_agent_config: dict[str, Any] = Field(default_factory=dict)


class UpdateAgentRegistrationRequest(BaseModel):
    description: str | None = Field(default=None)
    repo_url: str | None = Field(default=None)
    agent_description_path: str | None = Field(default=None)
    agent_description_content: str | None = Field(
        default=None,
        description="Re-upload AGENT_DESCRIPTION.md. Setting this also updates agent_description_uploaded_at.",
    )
    eval_command: str | None = Field(default=None)
    cloud_agent_type: CloudAgentType | None = Field(default=None)
    cloud_agent_config: dict[str, Any] | None = Field(default=None)


class AgentRegistrationFilter(NemoFilter):
    cloud_agent_type: CloudAgentType | None = Field(default=None)


AgentRegistrationPage = NemoListResponse[AgentRegistration]


# ---------------------------------------------------------------------------
# Insight
# ---------------------------------------------------------------------------


class CreateInsightRequest(BaseModel):
    name: str = Field(description="Human-readable identifier for the insight, unique within workspace.")
    agent: str = Field(description="AgentRegistration.name this insight is about.")
    description: str
    hypothesis: str = Field(default="")
    impact_estimate: float | None = Field(default=None)
    eval_dataset_row_refs: list[str] = Field(default_factory=list)
    experiment_refs: list[str] = Field(default_factory=list)


class UpdateInsightRequest(BaseModel):
    description: str | None = Field(default=None)
    hypothesis: str | None = Field(default=None)
    status: InsightStatus | None = Field(default=None)
    impact_estimate: float | None = Field(default=None)
    eval_dataset_row_refs: list[str] | None = Field(default=None)
    experiment_refs: list[str] | None = Field(default=None)


class InsightFilter(NemoFilter):
    agent: str | None = Field(default=None)
    status: InsightStatus | None = Field(default=None)


InsightPage = NemoListResponse[Insight]


# ---------------------------------------------------------------------------
# InsightTrace
# ---------------------------------------------------------------------------


class CreateInsightTraceRequest(BaseModel):
    insight: str = Field(description="Insight.name to attach the trace to.")
    trace_id: str = Field(description="intake trace.id of the trace being attached.")
    role: InsightTraceRole = Field(default=InsightTraceRole.EVIDENCE)
    note: str = Field(default="")


class UpdateInsightTraceRequest(BaseModel):
    role: InsightTraceRole | None = Field(default=None)
    note: str | None = Field(default=None)


class InsightTraceFilter(NemoFilter):
    insight: str | None = Field(default=None)
    trace_id: str | None = Field(default=None)
    role: InsightTraceRole | None = Field(default=None)


InsightTracePage = NemoListResponse[InsightTrace]
