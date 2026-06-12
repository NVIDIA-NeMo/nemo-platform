# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# SHM: megabyte/gigabyte scale only — Mi, Gi (binary) or M, G (decimal SI).
# Ki / Ti / Pi / Ei and other suffixes are not accepted for /dev/shm.
_SHM_QUANTITY_RE = re.compile(r"^([+-]?(?:\d+|\d*\.\d+)(?:[eE][+-]?\d+)?)(Mi|Gi|M|G)$")


class ContainerSpec(BaseModel):
    """
    Specification for a container configuration.

    Defines the container image and related configuration for job execution.
    """

    image: str | None = Field(default=None, min_length=1)
    """The container image to use for execution. When omitted, resolved from the execution profile's default_task_image or the platform CPU tasks image."""

    entrypoint: list[str] = Field(default_factory=list)
    """The entrypoint for the container as a list of strings (e.g., ['python', 'script.py']). This overrides a container's default entrypoint (e.g. ENTRYPOINT in Docker) if provided."""

    command: list[str] = Field(default_factory=list)
    """The command to execute as a list of strings (e.g., ['python', 'script.py']). This overrides a container's default commands (e.g. CMD in Docker) if provided."""


class ComputeResourceSpec(BaseModel):
    """Resource specification."""

    cpu: str | None = Field(default=None, description="CPU specification (e.g., '250m', '1', '2.5').")
    memory: str | None = Field(default=None, description="Memory specification (e.g., '128Mi', '1Gi', '512M').")


class ComputeResources(BaseModel):
    """Resource requirements matching k8s ResourceRequirements format."""

    requests: ComputeResourceSpec = Field(
        default_factory=ComputeResourceSpec, description="Minimum resources requested for the container."
    )

    limits: ComputeResourceSpec = Field(
        default_factory=ComputeResourceSpec, description="Maximum resources the container can use."
    )

    num_nodes: int = Field(default=1, ge=1, description="Number of nodes to use.")

    num_gpus: int | None = Field(default=None, description="Step requesting number of GPUs.")

    shm_size: str | None = Field(
        default=None,
        description="Shared memory (/dev/shm) size as a Kubernetes quantity (e.g. '1Gi', '4Gi'). "
        "Used for GPU and distributed-GPU job executors. When unset, defaults to 1Gi per allocated GPU.",
    )

    @field_validator("shm_size")
    @classmethod
    def validate_shm_size_quantity(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("shm_size cannot be empty or whitespace-only")
        if not _SHM_QUANTITY_RE.fullmatch(s):
            raise ValueError(
                "shm_size must use a megabyte/gigabyte-scale suffix: Mi, Gi, M, or G (e.g. '1Gi', '512Mi', '2G')."
            )
        return s


class TaskSpec(BaseModel):
    """
    Specification for a task to be executed.

    Defines the command and arguments for a job task.
    """

    command: list[str]
    """The command to execute as a list of strings (e.g., ['python', 'script.py'])."""

    args: list[str] | str
    """Arguments to pass to the command. Can be a list of strings or a single string."""


class CPUExecutionProvider(BaseModel):
    """
    CPU-based execution provider.

    Provides configuration for running jobs on CPU resources with
    resource requests and limits.
    """

    provider: Literal["cpu"] = "cpu"
    """The provider type, always 'cpu' for CPU execution."""

    profile: str = "default"
    """The execution profile to use. Defaults to 'default'."""

    container: ContainerSpec
    """Container specification defining the execution environment."""

    resources: ComputeResources = Field(
        default_factory=ComputeResources, description="Resource requests and limits for CPU execution."
    )


class GPUExecutionProvider(BaseModel):
    """
    GPU-based execution provider.

    Provides configuration for running jobs on GPU resources with
    resource requests and limits.
    """

    provider: Literal["gpu"] = "gpu"
    """The provider type, always 'gpu' for GPU execution."""

    profile: str = "default"
    """The execution profile to use. Defaults to 'default'."""

    container: ContainerSpec
    """Container specification defining the execution environment."""

    resources: ComputeResources = Field(
        default_factory=ComputeResources, description="Resource requests and limits for GPU execution."
    )


class DistributedGPUExecutionProvider(BaseModel):
    """
    GPU-based execution provider.

    Provides configuration for running jobs on GPU resources with
    resource requests and limits.
    """

    provider: Literal["gpu_distributed"] = "gpu_distributed"
    """The provider type, always 'gpu_distributed' for distributed GPU execution."""

    profile: str = "default"
    """The execution profile to use. Defaults to 'default'."""

    container: ContainerSpec
    """Container specification defining the execution environment."""

    resources: ComputeResources = Field(
        default_factory=ComputeResources, description="Resource requests and limits for distributed GPU execution."
    )


class SubprocessExecutionProvider(BaseModel):
    """Host subprocess execution provider."""

    provider: Literal["subprocess"] = "subprocess"
    """The provider type, always 'subprocess' for host subprocess execution."""

    profile: str = "default"
    """The execution profile to use. Defaults to 'default'."""

    command: list[str]
    """The host command to execute as a list of strings (e.g., ['python', '-m', 'my_task'])."""

    @model_validator(mode="after")
    def validate_command(self) -> "SubprocessExecutionProvider":
        if not self.command:
            raise ValueError("subprocess execution requires command to be set")
        return self


# Type alias for the current execution provider implementation
ExecutionProviderT = Union[
    CPUExecutionProvider, GPUExecutionProvider, DistributedGPUExecutionProvider, SubprocessExecutionProvider
]
"""Type alias representing the current execution provider type."""

# Discriminated union type for execution providers
Provider = Annotated[
    ExecutionProviderT,
    Field(discriminator="provider"),
]
"""
Discriminated union type for execution providers.

Uses the 'provider' field to determine the specific provider type.
Currently supports CPU execution providers, with extensibility for future provider types.
"""
