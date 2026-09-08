# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The gym_sandbox_daytona backend: ``nemo_gym.sandbox`` via Mini SWE Agent 2.

This backend drives NeMo Gym's provider-neutral sandbox API
(``nemo_gym.sandbox`` + ``DaytonaProvider`` from Gym PR #1377/#1513) through
the ``mini_swe_agent_2`` resource agent. Each SWE-bench task row creates a
Daytona sandbox via the Gym sandbox facade rather than Harbor's built-in
Daytona environment.

Distinct from:

- ``sandbox_k8s`` — Harbor on Kubernetes (agent-sandbox)
- ``gym_daytona`` — Harbor ``harbor_agent`` using Harbor's Daytona env

Requires a Gym checkout with the sandbox API merged (PR #1377) and Daytona
provider (open PR #1513), plus ``nemo-gym[sandbox]`` installed. The scaled-evals
validated refresh SHA is ``b6199c4c00dd55a356b7bacd0b01f342858d2298``.
"""

from __future__ import annotations

from collections.abc import Callable

from scaled_evals.api.settings import settings
from scaled_evals.dispatch.gym.backend import GymRunnerConfig, build_gym_runner_lifecycle
from scaled_evals.dispatch.gym.common import make_gym_submitter
from scaled_evals.dispatch.runtime_backend import (
    CallableRuntimeBackend,
    LaunchHandle,
    LaunchSpec,
    RuntimeStatus,
)
from scaled_evals.dispatch.sandbox_k8s import Runner, summarize_harbor_result


class GymSandboxDaytonaBackend(CallableRuntimeBackend):
    """Backend for Mini SWE Agent 2 + ``nemo_gym.sandbox`` on Daytona."""

    name = "gym_sandbox_daytona"

    def __init__(
        self,
        *,
        submitter: Callable[[LaunchSpec], LaunchHandle] | None = None,
        terminator: Callable[[LaunchHandle], None] | None = None,
        status_reader: Callable[[LaunchHandle], RuntimeStatus] | None = None,
    ) -> None:
        super().__init__(
            name=self.name,
            submitter=submitter,
            terminator=terminator,
            status_reader=status_reader,
            summarizer=summarize_harbor_result,
            launch_unavailable=(
                "gym_sandbox_daytona live submission is not wired; inject a submitter "
                "(integration point with nemo_gym.sandbox + mini_swe_agent_2)"
            ),
        )


def make_gym_sandbox_daytona_submitter(
    *,
    gym_dir: str,
    env_file: str,
    work_dir: str = "/tmp",
    runner: Runner | None = None,
) -> Callable[[LaunchSpec], LaunchHandle]:
    """Build the live submitter for Mini SWE Agent 2 on Daytona sandboxes."""
    return make_gym_submitter(
        backend_name=GymSandboxDaytonaBackend.name,
        gym_dir=gym_dir,
        env_file=env_file,
        work_dir=work_dir,
        runner=runner,
    )


def build_backend() -> GymSandboxDaytonaBackend:
    """Construct the gym_sandbox_daytona backend per settings."""
    if not settings.gym_sandbox_daytona_enabled:
        return GymSandboxDaytonaBackend()
    if not settings.gym_sandbox_daytona_env_file:
        raise RuntimeError(
            "GYM_SANDBOX_DAYTONA_ENABLED is set but GYM_SANDBOX_DAYTONA_ENV_FILE is "
            "not — point it at examples/gym-sandbox-daytona/targets/*.env."
        )
    lifecycle = build_gym_runner_lifecycle(
        GymRunnerConfig(
            backend_name=GymSandboxDaytonaBackend.name,
            mode="docker",
            image=settings.gym_runner_image,
            env_file=settings.gym_sandbox_daytona_env_file,
            work_dir=settings.gym_sandbox_daytona_work_dir,
            work_volume=settings.gym_sandbox_daytona_docker_volume,
            host_env_file=settings.gym_sandbox_daytona_host_env_file,
        )
    )
    return GymSandboxDaytonaBackend(
        submitter=lifecycle.submitter,
        status_reader=lifecycle.status_reader,
        terminator=lifecycle.terminator,
    )
