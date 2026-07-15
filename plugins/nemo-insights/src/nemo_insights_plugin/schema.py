# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request/response schemas for the insights plugin HTTP API."""

from datetime import datetime

from nemo_insights_plugin.entities import (
    AnalysisConfig,
    AnalysisConfigStatus,
    AnalysisRunStatus,
    Insight,
    InsightStatus,
)
from nemo_platform_plugin.schema import NemoListResponse
from pydantic import BaseModel, Field


class CreateInsightRequest(BaseModel):
    """Body for ``POST /insights``.

    ``status`` defaults to :attr:`InsightStatus.OPEN`; callers that want to
    mint an insight already in another lifecycle state set it explicitly.
    """

    title: str = Field(
        description=(
            "A short, human-readable sentence naming the core issue. The full "
            "problem statement goes in 'description'. The store's slug name is "
            "auto-generated, so no name is supplied here."
        ),
    )
    agent: str = Field(
        description="Name of the registered agent this insight is about.",
    )
    description: str = Field(
        description=("The problem statement: specific enough to act on. This is editable by the developer."),
    )
    status: InsightStatus = Field(default=InsightStatus.OPEN)
    trace_refs: list[str] = Field(default_factory=list)


class UpdateInsightRequest(BaseModel):
    """Body for ``PATCH /insights/{insight_id}``. Omitted fields are unchanged."""

    title: str | None = None
    agent: str | None = None
    description: str | None = None
    status: InsightStatus | None = None
    trace_refs: list[str] | None = None


InsightPage = NemoListResponse[Insight]


class UpdateAnalysisConfigRequest(BaseModel):
    """Body for ``PATCH /analysis-configs/{agent}``."""

    enabled: bool | None = None


class UpdateAnalysisRunStatusRequest(BaseModel):
    """Body for ``PATCH /analysis-run-statuses/{agent}``."""

    status: AnalysisConfigStatus | None = None
    last_successful_run_at: datetime | None = None
    last_attempted_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_submitted_job: str | None = None
    last_error: str | None = None


AnalysisConfigPage = NemoListResponse[AnalysisConfig]
AnalysisRunStatusPage = NemoListResponse[AnalysisRunStatus]
