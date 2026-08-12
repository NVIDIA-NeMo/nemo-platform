# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the nmp-rl compiler and container tasks.

Modeled after :mod:`nmp.unsloth.config`. Environment variables use the
``NMP_RL_`` prefix and drive image resolution and the multi-node shared-storage
gate for the ``PlatformJobSpec`` the plugin's ``RlJob.compile`` builds.
"""

from nmp.common.config import create_service_config_class, get_platform_config, get_service_config
from pydantic import Field


class RlConfig(create_service_config_class("rl")):  # type: ignore[misc]  # ty: ignore[unsupported-base]
    """Environment variables use the ``NMP_RL_`` prefix."""

    image_registry: str | None = Field(
        default=None,
        description=(
            "Registry host/path prefix for nmp-customizer-tasks and nmp-rl-training. "
            "Override via NMP_RL_IMAGE_REGISTRY; defaults to the platform's image registry."
        ),
    )
    training_image: str | None = Field(
        default=None,
        description="Override entire GPU training image (registry/name:tag).",
    )
    tasks_image: str | None = Field(
        default=None,
        description="Override entire CPU tasks image (registry/name:tag).",
    )

    default_job_resource_cpu_request: str = Field(default="1")
    default_job_resource_memory_request: str = Field(default="8Gi")
    default_job_resource_cpu_limit: str = Field(default="4")
    default_job_resource_memory_limit: str = Field(default="16Gi")

    default_training_execution_profile: str = Field(
        default="gpu",
        description="Default single-node GPU profile when training.execution_profile is omitted.",
    )
    default_distributed_execution_profile: str = Field(
        default="gpu_distributed",
        description="Default multi-node (num_nodes>1) distributed-GPU execution profile.",
    )

    multinode_shared_storage_path: str | None = Field(
        default=None,
        description=(
            "Shared filesystem path (e.g. an NFS mount) used as BASE_LOG_DIR for Ray's "
            "cross-node ENDED/barrier coordination. REQUIRED for multi-node jobs "
            "(num_nodes>1); compile() fails fast when unset. Single-node jobs ignore it."
        ),
    )

    sandboxed_gym_default: bool = Field(
        default=True,
        description=(
            "When true, GRPO jobs with custom environment filesets compile with "
            "env.nemo_gym.sandboxed=true (platform operator default)."
        ),
    )

    gym_runtime_image: str | None = Field(
        default=None,
        description=(
            "Image the Gym sandbox runs for sandboxed GRPO (registry/name:tag). "
            "Defaults to the nmp-rl-training image, which already carries NeMo-Gym and the "
            "per-environment venvs."
        ),
    )

    sandbox_allow_internet: bool = Field(
        default=False,
        description=(
            "Sets env.nemo_gym.sandbox.allow_internet. NeMo-RL owns which DNS suffixes that "
            "opens; cluster-private, node-local and metadata destinations stay denied either "
            "way. Sandboxed environments build their server venvs at spin-up and cannot reach "
            "a package index without it, so enable this on clusters that run user-supplied "
            "environments and have no internal mirror."
        ),
    )

    sandbox_cluster_capable: bool = Field(
        default=False,
        description=(
            "When false and sandboxed_gym_default is true, GRPO jobs with environment "
            "filesets fail at compile time unless the cluster has OpenSandbox available."
        ),
    )

    job_storage_pvc_claim: str | None = Field(
        default=None,
        description=(
            "Name of the shared job-storage PersistentVolumeClaim (the same claim the Jobs "
            "controller mounts at the job storage path). Sandboxed GRPO re-mounts that claim "
            "into the Gym host so the sandbox can read the downloaded environment and dataset, "
            "so it must be set on any cluster where sandbox_cluster_capable is true."
        ),
    )


config = get_service_config(RlConfig)
platform_config = get_platform_config()
