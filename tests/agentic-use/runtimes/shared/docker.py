# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility shim — Docker helpers were promoted to the Evaluator SDK.

Import from ``nemo_evaluator_sdk.agent_eval.runtimes.docker`` directly; this
module re-exports the same symbols so existing adapter imports keep working.
"""

from __future__ import annotations

from nemo_evaluator_sdk.agent_eval.runtimes.docker import (
    build_dockerfile,
    build_task_image,
    docker_image_exists,
    docker_run,
    redact_cmd_for_logging,
)

__all__ = [
    "build_dockerfile",
    "build_task_image",
    "docker_image_exists",
    "docker_run",
    "redact_cmd_for_logging",
]
