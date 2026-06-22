# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-trial metric scoring records and scoring diagnostics."""

from __future__ import annotations

from enum import Enum
from typing import Any

from nemo_platform.beta.evaluator.metrics.protocol import MetricOutput
from pydantic import BaseModel, ConfigDict, Field


class AgentEvalScoreStatus(str, Enum):
    """Status of metric scoring for one trial."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentEvalDiagnosticSeverity(str, Enum):
    """Severity level for a scoring diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AgentEvalDiagnostic(BaseModel):
    """Diagnostic emitted while scoring one trial with one metric."""

    model_config = ConfigDict(extra="forbid")

    severity: AgentEvalDiagnosticSeverity = Field(description="Severity of the diagnostic.")
    message: str = Field(description="Human-readable diagnostic message.")
    source: str | None = Field(
        default=None,
        description="Component or stage that produced the diagnostic, if known.",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured supporting details for the diagnostic.",
    )


class AgentEvalTaskScore(BaseModel):
    """Per-task, per-trial, per-metric scoring record: metric outputs, diagnostics, status, and metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this score record.")
    run_id: str = Field(description="Identifier of the run this score belongs to.")
    task_id: str = Field(description="Identifier of the task that was scored.")
    trial_id: str = Field(description="Identifier of the trial that was scored.")
    metric_type: str = Field(description="Task-local metric type (metric.type) that produced this score.")
    status: AgentEvalScoreStatus = Field(description="Status of this metric score.")
    outputs: list[MetricOutput] = Field(
        default_factory=list,
        description="Named metric outputs emitted for this trial/metric pair.",
    )
    diagnostics: list[AgentEvalDiagnostic] = Field(
        default_factory=list,
        description="Diagnostics emitted while scoring this trial with this metric.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata associated with the score.",
    )
