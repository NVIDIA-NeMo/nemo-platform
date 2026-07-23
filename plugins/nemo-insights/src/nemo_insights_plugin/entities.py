# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights plugin entity definitions — stored in the NeMo Platform entity store."""

from datetime import datetime
from enum import StrEnum

from nemo_platform_plugin.entity import NemoEntity
from pydantic import BaseModel, ConfigDict, Field


class InsightStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DELETED = "deleted"


class AnalysisConfigStatus(StrEnum):
    """Lifecycle state for periodic insights analysis of one agent."""

    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class EvalAuthorRunStatus(StrEnum):
    """Lifecycle state for an externally executed Eval Author run."""

    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvalAuthorRunStage(StrEnum):
    """Current producer stage for an Eval Author run."""

    INITIALIZING = "initializing"
    MATERIALIZING_TRACES = "materializing_traces"
    ANALYZING_TRACES = "analyzing_traces"
    DISCOVERING_RUNNER = "discovering_runner"
    AUTHORING_VERIFIER = "authoring_verifier"
    VALIDATING = "validating"
    PUBLISHING = "publishing"
    COMPLETED = "completed"


class EvalAuthorCaptureStatus(StrEnum):
    """Completeness of one captured artifact family."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class EvalAuthorConfigDetails(BaseModel):
    """Resolved Eval Author tuning parameters."""

    model_config = ConfigDict(extra="forbid")

    max_traces: int = Field(default=10, ge=1)
    max_summary_tokens: int = Field(default=80_000, ge=1)
    max_validation_repair_attempts: int = Field(default=5, ge=0, le=10)


class EvalAuthorInputs(BaseModel):
    """Small references to the inputs consumed by a run."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    task_template: str
    train_dataset: str
    validation_dataset: str
    trace_refs: list[str] = Field(default_factory=list)


class EvalAuthorModels(BaseModel):
    """Resolved model configuration used by the producer."""

    model_config = ConfigDict(extra="forbid")

    smart: str
    fast: str


class EvalAuthorProvenance(BaseModel):
    """Source and runner provenance for a run."""

    model_config = ConfigDict(extra="forbid")

    optimizer_branch: str
    optimizer_commit: str
    runner: str


class EvalAuthorOutputs(BaseModel):
    """Fileset-backed outputs and compact result metadata."""

    model_config = ConfigDict(extra="forbid")

    artifact_fileset: str | None = None
    insight_suite: str | None = None
    train_dataset: str | None = None
    validation_dataset: str | None = None
    metric_names: list[str] = Field(default_factory=list)
    train_task_count: int = Field(default=0, ge=0)
    validation_task_count: int = Field(default=0, ge=0)


class EvalAuthorCapture(BaseModel):
    """Capture completeness and redaction metadata."""

    model_config = ConfigDict(extra="forbid")

    prompt: EvalAuthorCaptureStatus = EvalAuthorCaptureStatus.UNAVAILABLE
    trajectory: EvalAuthorCaptureStatus = EvalAuthorCaptureStatus.UNAVAILABLE
    redactions: bool = False
    redacted_fields: list[str] = Field(default_factory=list)


class EvalAuthorValidation(BaseModel):
    """Verifier validation result and attempt count."""

    model_config = ConfigDict(extra="forbid")

    status: str = "not_run"
    attempt_count: int = Field(default=0, ge=0)


class Insight(NemoEntity, entity_type="insights_insight"):
    """A persistent problem, theme, or category of issues in the agent under test."""

    title: str = Field(
        description=(
            "A short, human-readable sentence naming the core issue common to "
            "the linked traces. Editable by the developer."
        ),
    )
    description: str = Field(
        description=(
            "The problem statement: specific enough to act on. Editable by the "
            "developer. A paragraph or two with detail on what exactly is going "
            "wrong, general enough to apply to many traces rather than to a "
            "single problematic instance."
        ),
    )
    agent: str = Field(
        description=(
            "Name of the registered agent this insight is about, or a local "
            "filesystem path (as a string) to the agent directory when running "
            "offline."
        ),
    )
    status: InsightStatus = Field(
        default=InsightStatus.OPEN,
        description=(
            "An insight starts as open. It can be resolved if the developer "
            "thinks the issue has been fixed. It can be deleted if the "
            "developer thinks the issue is not actually a problem or if it is "
            "not a good insight for their domain."
        ),
    )
    trace_refs: list[str] = Field(
        default_factory=list,
        description=(
            "Intake trace ids the analyst identified as evidence for this "
            "insight. This is used as evidence for the insight UI to "
            "communicate to the developer what traces triggered the issue, and "
            "can also be used to identify other similar traces that might "
            "experience the same issue."
        ),
    )


class EvalAuthorRun(NemoEntity, entity_type="insights_eval_author_run"):
    """Durable lifecycle and artifact index for one Eval Author attempt."""

    insight_id: str = Field(description="Insight that originated this run.")
    status: EvalAuthorRunStatus = Field(default=EvalAuthorRunStatus.CREATED)
    stage: EvalAuthorRunStage = Field(default=EvalAuthorRunStage.INITIALIZING)
    evaluator_type: str = Field(default="harbor")
    config: EvalAuthorConfigDetails
    inputs: EvalAuthorInputs
    models: EvalAuthorModels
    provenance: EvalAuthorProvenance
    outputs: EvalAuthorOutputs = Field(default_factory=EvalAuthorOutputs)
    capture: EvalAuthorCapture = Field(default_factory=EvalAuthorCapture)
    validation: EvalAuthorValidation = Field(default_factory=EvalAuthorValidation)
    summary: str = ""
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AnalysisConfig(NemoEntity, entity_type="insights_analysis_config"):
    """Per-agent opt-in state for framework-managed periodic analysis.

    The cadence is intentionally global insights configuration. This entity is
    only the per-agent switch. Machine-written run state lives on
    :class:`AnalysisRunStatus` so the controller never races the running job.
    """

    agent: str = Field(description="Name of the agent this analysis config targets.")
    enabled: bool = Field(
        default=True,
        description="Whether the periodic insights controller should analyze this agent.",
    )


class AnalysisRunStatus(NemoEntity, entity_type="insights_analysis_run_status"):
    """Machine-written run state for periodic analysis of one agent."""

    agent: str = Field(description="Name of the agent this run status targets.")
    status: AnalysisConfigStatus = Field(
        default=AnalysisConfigStatus.IDLE,
        description="Last known periodic analysis state for this agent.",
    )
    last_successful_run_at: datetime | None = Field(
        default=None,
        description=(
            "Cursor for incremental analysis. Scheduled runs only consider telemetry at or after this timestamp."
        ),
    )
    last_attempted_at: datetime | None = Field(
        default=None,
        description="When the controller or job last attempted analysis.",
    )
    last_completed_at: datetime | None = Field(
        default=None,
        description="When the last analysis attempt reached a terminal state.",
    )
    last_submitted_job: str = Field(
        default="",
        description="Most recent platform job name submitted for this agent.",
    )
    last_error: str = Field(
        default="",
        description="Most recent error or skip reason from scheduled analysis.",
    )
