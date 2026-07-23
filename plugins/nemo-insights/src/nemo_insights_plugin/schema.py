# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request/response schemas for the insights plugin HTTP API."""

from datetime import datetime

from nemo_insights_plugin.entities import (
    AnalysisConfig,
    AnalysisConfigStatus,
    AnalysisRunStatus,
    EvalAuthorCapture,
    EvalAuthorConfigDetails,
    EvalAuthorInputs,
    EvalAuthorModels,
    EvalAuthorOutputs,
    EvalAuthorProvenance,
    EvalAuthorRun,
    EvalAuthorRunStage,
    EvalAuthorRunStatus,
    EvalAuthorValidation,
    Insight,
    InsightStatus,
)
from nemo_platform_plugin.schema import NemoListResponse
from pydantic import BaseModel, ConfigDict, Field


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


class InsightListItem(Insight, entity_type="insights_insight"):
    """Insight representation used only in the paginated list response."""

    experiment_group_count: int | None = Field(
        default=None,
        description="Number of live experiment groups linked to this insight.",
    )
    last_seen_at: datetime | None = Field(
        default=None,
        description="Newest start timestamp among the insight's currently referenced traces.",
    )


InsightPage = NemoListResponse[InsightListItem]


class CreateEvalAuthorRunRequest(BaseModel):
    """Body for ``POST /eval-author-runs``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        description="Optional producer name. The service generates a short unique name when omitted.",
    )
    insight_id: str
    status: EvalAuthorRunStatus = EvalAuthorRunStatus.CREATED
    stage: EvalAuthorRunStage = EvalAuthorRunStage.INITIALIZING
    evaluator_type: str = "harbor"
    config: EvalAuthorConfigDetails
    inputs: EvalAuthorInputs
    models: EvalAuthorModels
    provenance: EvalAuthorProvenance
    outputs: EvalAuthorOutputs = Field(default_factory=EvalAuthorOutputs)
    capture: EvalAuthorCapture = Field(default_factory=EvalAuthorCapture)
    validation: EvalAuthorValidation = Field(default_factory=EvalAuthorValidation)
    summary: str = ""
    error: str | None = None


class UpdateEvalAuthorRunRequest(BaseModel):
    """Body for ``PATCH /eval-author-runs/{run_id}``; omitted fields are unchanged."""

    model_config = ConfigDict(extra="forbid")

    status: EvalAuthorRunStatus | None = None
    stage: EvalAuthorRunStage | None = None
    outputs: EvalAuthorOutputs | None = None
    capture: EvalAuthorCapture | None = None
    validation: EvalAuthorValidation | None = None
    summary: str | None = None
    error: str | None = None


EvalAuthorRunPage = NemoListResponse[EvalAuthorRun]


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
