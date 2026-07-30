# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Strict wire contracts for the bounded Experimentalist Harbor bridge."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import EvaluationResult
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Sha256Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    """Base model that rejects authority hidden in unknown request fields."""

    model_config = ConfigDict(extra="forbid")


class RunProfile(StrictModel):
    """Host-owned Harbor resource and timeout policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempts: int
    concurrency: int
    retries: int
    agent_timeout_multiplier: float
    verifier_timeout_multiplier: float
    setup_timeout_multiplier: float
    build_timeout_multiplier: float


class EnvelopeTask(StrictModel):
    """One generated task mapped to a trusted host-owned base task."""

    task_id: Identifier
    base_task_id: Identifier


class EvaluationEnvelope(StrictModel):
    """Content-addressed task envelope selected by a request."""

    id: Identifier
    digest: Sha256Digest
    tasks: list[EnvelopeTask] = Field(min_length=1, max_length=1024)

    @field_validator("tasks")
    @classmethod
    def unique_task_ids(cls, value: list[EnvelopeTask]) -> list[EnvelopeTask]:
        """Reject ambiguous output directories."""
        task_ids = [task.task_id for task in value]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("envelope tasks must have unique task_id values")
        return value


class ArchiveReference(StrictModel):
    """Digest of one multipart archive after safe extraction."""

    digest: Sha256Digest


class EvaluationSubmission(StrictModel):
    """Only caller-controlled data accepted for a Harbor evaluation."""

    schema_version: Literal[1] = 1
    request_id: Identifier
    envelope: EvaluationEnvelope
    candidate: ArchiveReference
    overlay: ArchiveReference | None = None
    run_profile: Literal["smoke", "standard"] = "standard"


class EvaluationState(StrEnum):
    """Lifecycle exposed to the sandbox."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvaluationAccepted(StrictModel):
    """Submission acknowledgement."""

    job_id: Identifier
    state: Literal[EvaluationState.PENDING] = EvaluationState.PENDING


class EvaluationStatus(StrictModel):
    """Small polling response with sanitized failures."""

    job_id: Identifier
    state: EvaluationState
    result: EvaluationResult | None = None
    error: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> EvaluationStatus:
        """Keep result and error fields consistent with state."""
        if self.state == EvaluationState.COMPLETED and self.result is None:
            raise ValueError("completed evaluation status requires result")
        if self.state != EvaluationState.COMPLETED and self.result is not None:
            raise ValueError("only completed evaluation status may include result")
        if self.state == EvaluationState.FAILED and not self.error:
            raise ValueError("failed evaluation status requires error")
        if self.state != EvaluationState.FAILED and self.error is not None:
            raise ValueError("only failed evaluation status may include error")
        return self


class DependencyStartRequest(StrictModel):
    """Start one trusted task environment for dependency analysis."""

    schema_version: Literal[1] = 1
    request_id: Identifier
    envelope_id: Identifier
    envelope_digest: Sha256Digest
    task_id: Identifier
    base_task_id: Identifier
    overlay_digest: Sha256Digest | None = None


class DependencySession(StrictModel):
    """Opaque capability for one bridge-owned task environment."""

    session_id: Identifier
    capability_token: str = Field(min_length=32, max_length=256)


class DependencyExecRequest(StrictModel):
    """A bounded command inside an existing bridge-owned environment."""

    command: str = Field(min_length=1, max_length=65_536)
    stdin: str | None = Field(default=None, max_length=1_048_576)
    timeout_sec: int = Field(default=30, ge=1, le=3600)


class DependencyExecResponse(StrictModel):
    """Capped command output."""

    stdout: str = Field(default="", max_length=30_064)
    stderr: str = Field(default="", max_length=30_064)
    returncode: int
