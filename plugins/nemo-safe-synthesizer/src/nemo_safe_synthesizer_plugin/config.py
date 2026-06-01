# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for the Safe Synthesizer plugin."""

from typing import ClassVar, Literal

from nemo_platform_plugin.config import NemoConfig
from pydantic import Field


class SafeSynthesizerConfig(NemoConfig):
    """Configuration for Safe Synthesizer plugin API and task compilation."""

    plugin_name: ClassVar[str] = "safe_synthesizer"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Safe Synthesizer plugin."

    host: str = "0.0.0.0"
    port: int = 8000
    entrypoint: list[str] = Field(
        default_factory=lambda: ["python", "-m", "nemo_safe_synthesizer_plugin.tasks.safe_synthesizer"]
    )
    job_mode: Literal["subprocess-local", "container"] = "subprocess-local"
    job_executor_profile: str = "default"
    container_image: str = "nmp-gpu-tasks"
    runtime_venv: str = ".nemo/safe-synthesizer-runtime"
    runtime_package: str = "nemo-safe-synthesizer[engine,cu129]==0.1.1"
    runtime_python_version: str = "3.11"
    runtime_python: str | None = None
    default_job_resource_memory_request: str = "16G"
    default_job_resource_cpu_request: str = "4"
    default_job_resource_memory_limit: str = "16G"
    default_job_resource_cpu_limit: str = "4"


def get_config() -> SafeSynthesizerConfig:
    """Return the Safe Synthesizer plugin configuration singleton."""
    return SafeSynthesizerConfig.get()


config = get_config()
