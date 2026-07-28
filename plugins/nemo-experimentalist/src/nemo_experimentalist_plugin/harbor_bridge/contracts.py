# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Narrow wire contract between Experimentalist and the Harbor bridge."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskId = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]


class HarborBridgeRequest(BaseModel):
    """Bounded Harbor run parameters accepted from an OpenShell sandbox."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    task_ids: list[TaskId] = Field(min_length=1, max_length=1024)
    n_attempts: int = Field(default=1, ge=1, le=8)
    n_concurrent_trials: int = Field(default=4, ge=1, le=16)
    agent_model_name: str | None = Field(default=None, min_length=1, max_length=256)
    agent_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    verifier_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    agent_setup_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)
    environment_build_timeout_multiplier: float | None = Field(default=1.0, ge=0.1, le=10.0)

    @field_validator("task_ids")
    @classmethod
    def validate_unique_task_ids(cls, value: list[str]) -> list[str]:
        """Reject ambiguous selections before they become filesystem inputs."""
        if len(set(value)) != len(value):
            raise ValueError("task_ids must not contain duplicates")
        return value
