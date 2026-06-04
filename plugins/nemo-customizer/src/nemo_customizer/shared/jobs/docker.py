# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker runtime checks for container-submit customization jobs."""

from __future__ import annotations

from nemo_platform_plugin.config import NemoPlatformConfig, Runtime, validate_docker_available
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError


def require_docker_runtime(backend_display_name: str) -> None:
    """Refuse to compile when the platform is not configured for Docker execution."""
    platform_config = NemoPlatformConfig.get()
    if platform_config.runtime != Runtime.DOCKER:
        raise PlatformJobCompilationError(
            f"{backend_display_name} training requires platform.runtime: docker with GPU-backed container execution.",
        )

    if not validate_docker_available():
        raise PlatformJobCompilationError(
            f"{backend_display_name} training requires a reachable Docker daemon (platform.runtime: docker).",
        )
