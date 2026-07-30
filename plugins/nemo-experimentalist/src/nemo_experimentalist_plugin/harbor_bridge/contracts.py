# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Narrow wire contract between Experimentalist and the Harbor bridge."""

from typing import Annotated

from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    EnvelopeId,
    EnvelopeTaskSelection,
    Sha256Digest,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskId = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
DEPENDENCY_OUTPUT_LIMIT_CHARS = 30_000


class HarborBridgeRequest(BaseModel):
    """Bounded Harbor run parameters accepted from an OpenShell sandbox."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    envelope_id: EnvelopeId
    envelope_digest: Sha256Digest
    tasks: list[EnvelopeTaskSelection] = Field(min_length=1, max_length=1024)
    candidate_digest: Sha256Digest
    overlay_digest: Sha256Digest | None = None
    scorer_identity: Sha256Digest | None = None
    n_attempts: int = Field(default=1, ge=1, le=8)
    n_concurrent_trials: int = Field(default=4, ge=1, le=16)
    agent_model_name: str | None = Field(default=None, min_length=1, max_length=256)
    agent_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    verifier_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    agent_setup_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    environment_build_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)

    @field_validator("tasks")
    @classmethod
    def validate_unique_task_ids(cls, value: list[EnvelopeTaskSelection]) -> list[EnvelopeTaskSelection]:
        """Reject ambiguous selections before they become filesystem inputs."""
        task_ids = [task.task_id for task in value]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("tasks must not contain duplicate task ids")
        return value

    @property
    def task_ids(self) -> list[str]:
        """Return materialized task ids for evaluator compatibility."""
        return [task.task_id for task in self.tasks]


class HarborDependencyRequest(BaseModel):
    """Bounded request to start one Harbor task environment."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    envelope_id: EnvelopeId
    envelope_digest: Sha256Digest
    task_id: TaskId
    base_task_id: TaskId
    overlay_digest: Sha256Digest | None = None
    force_build: bool = True
    run_healthcheck: bool = True
    build_timeout_sec: int | None = Field(default=None, ge=1, le=3600)


class HarborDependencySessionResponse(BaseModel):
    """Opaque handle for one bridge-owned Harbor task environment."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    capability_token: str = Field(min_length=16, max_length=256)


class HarborDependencyExecRequest(BaseModel):
    """One shell command executed inside a bridge-owned task environment."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=65_536)
    stdin: str | None = Field(default=None, max_length=1_048_576)
    timeout_sec: int = Field(default=30, ge=1, le=3600)


class HarborDependencyExecResponse(BaseModel):
    """Captured result from a task-environment command."""

    model_config = ConfigDict(extra="forbid")

    stdout: str = Field(default="", max_length=DEPENDENCY_OUTPUT_LIMIT_CHARS + 64)
    stderr: str = Field(default="", max_length=DEPENDENCY_OUTPUT_LIMIT_CHARS + 64)
    returncode: int
