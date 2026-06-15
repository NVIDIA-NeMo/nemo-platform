# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared schemas for the Jobs service."""

from typing import Optional, Self

from nmp.common.entities.constants import NAME_PATTERN, NAME_PATTERN_DESCRIPTION
from nmp.common.jobs.constants import PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.core.jobs.app.providers import ExecutorKind, Provider
from pydantic import BaseModel, ConfigDict, Field, model_validator

# =============================================================================
# Domain Models (shared by entities, dispatcher, and API)
# =============================================================================


class PlatformJobSecretEnvironmentVariableRef(BaseModel):
    """Reference to a secret to populate an environment variable for a job step."""

    name: str = Field(description="The name of the secret to reference")


class PlatformJobEnvironmentVariable(BaseModel):
    """Environment variable for a job step"""

    name: str = Field(description="The environment variable name")
    value: Optional[str] = Field(default=None, description="The environment variable value")
    from_secret: Optional[PlatformJobSecretEnvironmentVariableRef] = Field(
        default=None, description="Reference to a secret environment variable to populate the environment variable"
    )

    @model_validator(mode="after")
    def validate_self(self) -> Self:
        # Ensure one of value or from_secret is provided
        if self.value is None and self.from_secret is None:
            raise ValueError("Either value or from_secret must be provided for environment variables.")

        # Ensure only one of value or from_secret is provided
        if self.value is not None and self.from_secret is not None:
            raise ValueError("Only one of value or from_secret can be provided for environment variables.")

        return self


class StepLifecycle(BaseModel):
    """Controller-level lifecycle configuration for a job step.

    These settings control how the jobs controller manages the step,
    as opposed to ``config`` which is the task payload forwarded to
    the container.
    """

    staleness_timeout_seconds: int = Field(
        default=0,
        description="If every active task in the step goes this many seconds without an update, the step is terminated. "
        "A value of 0 disables staleness detection.",
    )


class PlatformJobStepSpec(BaseModel):
    """Specification for a single step in a platform job."""

    name: str = Field(
        description=f"The name of the step. Must be unique for all steps in a job. {NAME_PATTERN_DESCRIPTION}",
        pattern=NAME_PATTERN,
        examples=["preprocess", "train-model", "eval-step-v1"],
    )
    environment: Optional[list[PlatformJobEnvironmentVariable]] = Field(
        default=None, description="Environment variables for the step"
    )
    executor: Provider = Field(description="The executor for the step")
    config: dict = Field(default_factory=dict, description="Configuration for the step")
    lifecycle: StepLifecycle = Field(
        default_factory=StepLifecycle, description="Lifecycle configuration settings for the step"
    )

    @property
    def requires_persistent_storage(self) -> bool:
        """
        Determine if the step requires persistent storage.

        This is determined by checking if the step has an environment variable
        matching the value of PERSISTENT_JOB_STORAGE_PATH_ENVVAR.
        """
        for envvar in self.environment or []:
            if envvar.name == PERSISTENT_JOB_STORAGE_PATH_ENVVAR:
                return True
        return False

    model_config = ConfigDict(regex_engine="python-re")


class PlatformJobSpec(BaseModel):
    """Specification for a platform job, containing steps and secrets."""

    steps: list[PlatformJobStepSpec] = Field(description="List of steps to be executed in the job")

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        # Ensure there is at least one step.
        if not self.steps:
            raise ValueError("At least one step is required in the job specification.")

        # Ensure that each step has a unique name.
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Each step must have a unique name.")
        return self


# =============================================================================
# Misc Schemas
# =============================================================================


ProviderRef = str
ProfileRef = str
BackendRef = str


class BaseExecutionProfile(BaseModel):
    """Execution configuration for a job."""

    provider: ProviderRef = Field(
        default="cpu",
        description="The compute provider for the executor, e.g., cpu, gpu",
    )
    profile: str = Field(
        default="default",
        description="The profile name for the executor, e.g., high_priority_a100, low_priority, etc.",
    )
    kind: ExecutorKind = Field(
        default="container",
        description="The executor payload shape this profile expects: 'container' or 'subprocess'.",
    )

    @property
    def supports_persistent_storage(self) -> bool:
        """Indicates if the execution profile supports persistent storage."""
        return False

    def __str__(self) -> str:
        return f"{self.profile}:{self.provider}"
