# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime backend plugin for NeMo Gym integrations."""

from __future__ import annotations

from typing import Any

from scaled_evals.api.settings import settings
from scaled_evals.dispatch.gym.daytona import GymDaytonaBackend
from scaled_evals.dispatch.gym.daytona import build_backend as build_gym_daytona_backend
from scaled_evals.dispatch.gym.sandbox_daytona import GymSandboxDaytonaBackend
from scaled_evals.dispatch.gym.sandbox_daytona import (
    build_backend as build_gym_sandbox_daytona_backend,
)
from scaled_evals.dispatch.gym.sandbox_opensandbox import GymSandboxOpenSandboxBackend
from scaled_evals.dispatch.gym.sandbox_opensandbox import (
    build_backend as build_gym_sandbox_opensandbox_backend,
)
from scaled_evals.dispatch.paths import setting_evaluation_dir
from scaled_evals.dispatch.runtime_backend import (
    RuntimeBackendCapabilities,
    RuntimeBackendRegistration,
)

__all__ = ["register_runtime_backends"]


def register_runtime_backends(registry: Any) -> None:
    """Register Gym-backed runtimes with a RuntimeBackendRegistry-like object."""
    registry.register(
        RuntimeBackendRegistration(
            name=GymDaytonaBackend.name,
            factory=build_gym_daytona_backend,
            description="Harbor through NeMo Gym on Daytona.",
            capabilities=RuntimeBackendCapabilities(
                artifact_root=setting_evaluation_dir(settings, "gym_daytona_work_dir"),
                dispatch_work_dir=setting_evaluation_dir(settings, "gym_daytona_work_dir"),
                dispatch_log_name="gym.log",
                runner_container_prefix="gym",
                extra_dispatch_log_names=("ng_run.log",),
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            name=GymSandboxDaytonaBackend.name,
            factory=build_gym_sandbox_daytona_backend,
            description="NeMo Gym sandbox API through Daytona.",
            capabilities=RuntimeBackendCapabilities(
                artifact_root=setting_evaluation_dir(settings, "gym_sandbox_daytona_work_dir"),
                dispatch_work_dir=setting_evaluation_dir(settings, "gym_sandbox_daytona_work_dir"),
                dispatch_log_name="gym.log",
                runner_container_prefix="gym",
                extra_dispatch_log_names=("ng_run.log",),
            ),
        )
    )
    registry.register(
        RuntimeBackendRegistration(
            name=GymSandboxOpenSandboxBackend.name,
            factory=build_gym_sandbox_opensandbox_backend,
            description="NeMo Gym sandbox API through OpenSandbox.",
            capabilities=RuntimeBackendCapabilities(
                artifact_root=setting_evaluation_dir(settings, "gym_sandbox_opensandbox_work_dir"),
                dispatch_work_dir=setting_evaluation_dir(settings, "gym_sandbox_opensandbox_work_dir"),
                dispatch_log_name="gym.log",
                runner_container_prefix="gym",
                extra_dispatch_log_names=("ng_run.log",),
            ),
        )
    )
