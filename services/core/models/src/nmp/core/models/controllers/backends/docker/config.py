# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration model for docker backend."""

import os
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

MODELS_DOCKER_NETWORKING_MODE = os.getenv("MODELS_DOCKER_NETWORKING_MODE", "local")
MODELS_DOCKER_NETWORK = os.getenv("MODELS_DOCKER_NETWORK", "")
MODELS_DOCKER_CONTAINER_NAME = os.getenv("MODELS_DOCKER_CONTAINER_NAME", "")
MODELS_DOCKER_HOST_SERVICE_NAME = os.getenv("MODELS_DOCKER_HOST_SERVICE_NAME", "localhost")
MODELS_DOCKER_PORT_RANGE_START = os.getenv("MODELS_DOCKER_PORT_RANGE_START", "49152")
MODELS_DOCKER_PORT_RANGE_END = os.getenv("MODELS_DOCKER_PORT_RANGE_END", "49652")
MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE = os.getenv("MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE", "")
MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE_PER_GPU = os.getenv("MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE_PER_GPU", "")


class DockerNetworkingMode(str, Enum):
    """Networking mode for the Docker backend.

    Determines how NeMo Platform communicates with NIM containers.
    """

    LOCAL = "local"
    """Local development: NeMo Platform runs on host, NIMs get ports mapped to localhost."""

    DOND = "dond"
    """Docker on Docker: NeMo Platform runs in a container with Docker socket mounted.
    NIMs are sibling containers and communicate via a shared Docker network."""

    DIND = "dind"
    """Docker in Docker: NeMo Platform runs in a container with a DinD sidecar.
    NIMs run inside DinD and communicate via port forwarding through the DinD service."""


class DockerBackendConfig(BaseModel):
    """
    Configuration for the Docker backend.
    """

    default_nimservice_image: str = Field(
        default="nvcr.io/nim/nvidia/llm-nim",
        description="Default NIM image when none is specified (multi-LLM image)",
    )

    default_nimservice_image_tag: str = Field(
        default="1.13.1",
        description="Default NIM image tag when none is specified",
    )

    default_vllm_image: str = Field(
        default="vllm/vllm-openai",
        description="Default vLLM image when none is specified for engine='vllm'",
    )

    default_vllm_image_tag: str = Field(
        default="v0.22.1",
        description="Default vLLM image tag when none is specified for engine='vllm'",
    )

    nim_guided_decoding_backend: str = Field(
        default="outlines",
        description="NIM guided decoding backend",
    )

    peft_source: str = Field(
        default="",
        description="PEFT/LoRA source URL for models service",
    )

    peft_refresh_interval: int = Field(
        default=30,
        description="PEFT/LoRA refresh interval in seconds",
    )

    files_auth_secret: str = Field(
        default="files-hf-token",
        description="Secret name for Files service authentication",
    )

    docker_timeout: int = Field(
        default=600,
        description="Docker client timeout in seconds for long-running operations (default: 10 minutes)",
    )

    # ==========================================================================
    # Networking configuration
    # ==========================================================================

    models_docker_networking_mode: Literal["local", "dond", "dind"] = Field(
        default=MODELS_DOCKER_NETWORKING_MODE,
        description="Networking mode for NIM containers: "
        "'local' (port forwarding to localhost for local dev), "
        "'dond' (container names on shared network for quickstart), "
        "'dind' (port forwarding to docker service for DinD setups).",
    )

    models_docker_network: str = Field(
        default=MODELS_DOCKER_NETWORK,
        description="Docker network name for 'dond' mode. NIMs will join this network to communicate "
        "with the NeMo Platform container. Required when MODELS_DOCKER_NETWORKING_MODE='dond'. "
        "Quickstart sets this automatically via MODELS_DOCKER_NETWORK env var.",
    )

    models_docker_container_name: str = Field(
        default=MODELS_DOCKER_CONTAINER_NAME,
        description="Container name for 'dond' mode. Used to replace localhost in URLs passed to NIMs "
        "so they can reach services via the Docker network. "
        "Quickstart sets this automatically via MODELS_DOCKER_CONTAINER_NAME env var.",
    )

    models_docker_host_service_name: str = Field(
        default=MODELS_DOCKER_HOST_SERVICE_NAME,
        description="Hostname for port forwarding in 'dind' mode. Typically 'localhost' or the "
        "DinD service name. Used to construct URLs like http://{hostname}:{port}.",
    )

    models_docker_port_range_start: int = Field(
        default=int(MODELS_DOCKER_PORT_RANGE_START),
        description="Start of port range for port forwarding (inclusive). "
        "Defaults to start of IANA dynamic/ephemeral port range.",
    )

    models_docker_port_range_end: int = Field(
        default=int(MODELS_DOCKER_PORT_RANGE_END),
        description="End of port range for port forwarding (inclusive). "
        "Defaults to 500-port range within IANA dynamic/ephemeral range.",
    )

    huggingface_model_puller: str = Field(
        default="nvcr.io/nvidia/nemo-microservices/nds-v2-huggingface-cli:25.10",
        description="HuggingFace model puller image for downloading SFT model weights from Files service",
    )

    model_puller_timeout: int = Field(
        default=1800,
        description="Timeout in seconds for the model puller container to complete (default: 30 minutes)",
    )

    model_puller_download_timeout: int = Field(
        default=7200,
        description="Per-file HTTP download timeout in seconds for the model puller (HF_HUB_DOWNLOAD_TIMEOUT). "
        "Increase if large model files fail with IncompleteRead/ChunkedEncodingError (default: 2 hours).",
    )

    model_puller_max_workers: int = Field(
        default=1,
        ge=1,
        le=16,
        description="Max concurrent file downloads in the model puller (hf download --max-workers). "
        "Default 1 (sequential) reduces IncompleteRead/ChunkedEncodingError on slow or flaky links; increase for speed.",
    )

    model_puller_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of retries when the puller fails with a transient error (IncompleteRead, "
        "ChunkedEncodingError, connection broken). Same volume is reused so partial downloads can be completed.",
    )

    busybox_image: str = Field(
        default="busybox",
        description="BusyBox image repository used for helper containers (permissions/find/chown).",
    )

    busybox_image_tag: str = Field(
        default="latest",
        description="BusyBox image tag used for helper containers.",
    )

    # ==========================================================================
    # PENDING timeout and crash loop detection
    # ==========================================================================

    pending_timeout_seconds: int = Field(
        default=7200,
        ge=60,
        description="Maximum time (in seconds) a deployment may stay in PENDING before being "
        "transitioned to ERROR. Default: 7200 (2 hours).",
    )

    max_restart_count: int = Field(
        default=5,
        ge=1,
        description="Maximum number of container restarts before a PENDING deployment is "
        "transitioned to ERROR (crash loop detection). Default: 5.",
    )

    nim_multi_gpu_shm_size: str = Field(
        default="",
        description="Optional fixed shared memory size (/dev/shm) for multi-GPU NIM containers. "
        "If set, overrides the per-GPU calculation. Leave empty to use shm_size_per_gpu x GPU count. "
        "Override via MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE env. Format: e.g. '2g', '4g'.",
    )

    nim_multi_gpu_shm_size_per_gpu: int = Field(
        default=1024,
        ge=1,
        description="Shared memory size (/dev/shm) per GPU in megabytes for multi-GPU NIM containers. "
        "Total shm = this value x GPU count (e.g. 1024 x 2 GPUs = 2048m). "
        "Override via MODELS_DOCKER_NIM_MULTI_GPU_SHM_SIZE_PER_GPU env (integer string).",
    )
