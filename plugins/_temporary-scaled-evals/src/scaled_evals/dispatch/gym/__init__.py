# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Gym dispatch backends (Daytona, Docker runner, shared CLI helpers)."""

from scaled_evals.dispatch.gym.common import build_gym_argv
from scaled_evals.dispatch.gym.daytona import (
    GymDaytonaBackend,
    make_gym_daytona_submitter,
)
from scaled_evals.dispatch.gym.daytona import (
    build_backend as build_gym_daytona_backend,
)
from scaled_evals.dispatch.gym.docker import (
    build_docker_run_and_collect_argv,
    launch_gym_runner_container,
    make_gym_docker_submitter,
)
from scaled_evals.dispatch.gym.sandbox_daytona import (
    GymSandboxDaytonaBackend,
    make_gym_sandbox_daytona_submitter,
)
from scaled_evals.dispatch.gym.sandbox_daytona import (
    build_backend as build_gym_sandbox_daytona_backend,
)
from scaled_evals.dispatch.gym.sandbox_opensandbox import (
    GymSandboxOpenSandboxBackend,
    make_gym_sandbox_opensandbox_submitter,
)
from scaled_evals.dispatch.gym.sandbox_opensandbox import (
    build_backend as build_gym_sandbox_opensandbox_backend,
)

__all__ = [
    "GymDaytonaBackend",
    "GymSandboxDaytonaBackend",
    "GymSandboxOpenSandboxBackend",
    "build_docker_run_and_collect_argv",
    "build_gym_argv",
    "build_gym_daytona_backend",
    "build_gym_sandbox_daytona_backend",
    "build_gym_sandbox_opensandbox_backend",
    "launch_gym_runner_container",
    "make_gym_daytona_submitter",
    "make_gym_docker_submitter",
    "make_gym_sandbox_daytona_submitter",
    "make_gym_sandbox_opensandbox_submitter",
]
