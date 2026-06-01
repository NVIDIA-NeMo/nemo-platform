# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the NeMo Jailbreak Detect plugin.

Override via environment variables (highest priority) or the Helm
``platformConfig.jailbreak-detect`` section:

    NMP_JAILBREAK_DETECT_SERVER_IMAGE=...
    NMP_JAILBREAK_DETECT_DEFAULT_DEVICE=cpu
    NMP_JAILBREAK_DETECT_DEFAULT_BACKEND=docker
"""

from __future__ import annotations

from typing import ClassVar, Literal

from nemo_platform_plugin.config import NemoConfig
from pydantic import Field


class JailbreakDetectConfig(NemoConfig):
    """Configuration for the NeMo Platform jailbreak-detection plugin."""

    plugin_name: ClassVar[str] = "jailbreak-detect"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform jailbreak-detection plugin."

    server_image: str = Field(
        default="nemo/jailbreak-detect:0.1.0",
        description="Container image for the self-hosted jailbreak-detection model server.",
    )
    default_device: str = Field(
        default="cpu",
        description='Device the embedder runs on inside the server ("cpu", "cuda:0", ...).',
    )
    default_backend: Literal["docker", "jobs"] = Field(
        default="docker",
        description="Deployment backend used when an entity does not specify one.",
    )
    default_port: int = Field(
        default=8000,
        gt=0,
        description="Container port the model server listens on.",
    )
    model_cache_dir: str = Field(
        default="/opt/nemo/jailbreak-detect/cache",
        description="Host path mounted into the container for the model cache.",
    )
    controller_interval_seconds: float = Field(
        default=10.0,
        gt=0,
        description="How often the deployment controller reconciles, in seconds.",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Timeout for classify/health requests proxied or probed by the plugin.",
    )
