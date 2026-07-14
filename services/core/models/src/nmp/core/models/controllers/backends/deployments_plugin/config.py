# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the deployments-plugin models backend."""

from pydantic import BaseModel, Field


class DeploymentsPluginConfig(BaseModel):
    default_executor: str | None = None
    docker_executor: str | None = None
    k8s_executor: str | None = None
    pending_timeout_seconds: int = Field(
        default=7200,
        ge=60,
        description="Maximum seconds a deployment may stay PENDING before ERROR.",
    )
    max_restart_count: int = 5
    default_storage_class: str | None = None
    default_pvc_size: str = "200Gi"
    default_nimservice_image: str = "nvcr.io/nim/meta/llama-3.1-8b-instruct"
    default_nimservice_image_tag: str = "1.8.5"
    default_vllm_image: str = "vllm/vllm-openai"
    default_vllm_image_tag: str = "v0.8.5"
    default_user_id: int | None = 1000
    default_group_id: int | None = 2000
    default_vllm_user_id: int | None = 2000
    default_vllm_group_id: int | None = 0
    peft_refresh_interval: int = 30
    lora_sidecar_image_name: str = "nmp-api"
    lora_sidecar_command: list[str] = Field(
        default_factory=lambda: ["nemo", "services", "run", "--sidecars", "adapters"]
    )
    lora_sidecar_args: list[str] = Field(default_factory=list)
    busybox_image: str = Field(
        default="docker.io/library/busybox",
        description="BusyBox image repository for LoRA cache init containers. "
        "Fully qualified so it resolves on runtimes that block docker.io short names.",
    )
    busybox_image_tag: str = Field(
        default="latest",
        description="BusyBox image tag for LoRA cache init containers.",
    )
    delete_wait_seconds: float = Field(default=5.0, gt=0)
    delete_poll_seconds: float = Field(default=0.5, gt=0)


class DeploymentsPluginBackendConfigModel(DeploymentsPluginConfig):
    """Flat registry configuration, including the enablement switch."""

    enabled: bool = False
