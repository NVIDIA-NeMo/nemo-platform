# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The gym_sandbox_opensandbox backend: ``nemo_gym.sandbox`` via OpenSandbox.

This backend is the NeMo RL cluster-sandbox sibling of
:mod:`scaled_evals.dispatch.gym.sandbox_daytona`. The runner still starts Gym
locally inside a service-owned container or host checkout, but the Gym sandbox
provider talks to an OpenSandbox cell endpoint instead of Daytona.
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


class GymSandboxOpenSandboxBackend(CallableRuntimeBackend):
    """Backend for Mini SWE Agent 2 + ``nemo_gym.sandbox`` on OpenSandbox."""

    name = "gym_sandbox_opensandbox"

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
                "gym_sandbox_opensandbox live submission is not wired; inject a "
                "submitter (integration point with nemo_gym.sandbox + OpenSandbox)"
            ),
        )


def make_gym_sandbox_opensandbox_submitter(
    *,
    gym_dir: str,
    env_file: str,
    work_dir: str = "/tmp",
    runner: Runner | None = None,
) -> Callable[[LaunchSpec], LaunchHandle]:
    """Build the live submitter for Mini SWE Agent 2 on OpenSandbox."""
    return make_gym_submitter(
        backend_name=GymSandboxOpenSandboxBackend.name,
        gym_dir=gym_dir,
        env_file=env_file,
        work_dir=work_dir,
        runner=runner,
    )


def build_backend() -> GymSandboxOpenSandboxBackend:
    """Construct the gym_sandbox_opensandbox backend per settings."""
    if not settings.gym_sandbox_opensandbox_enabled:
        return GymSandboxOpenSandboxBackend()
    if not settings.gym_sandbox_opensandbox_env_file:
        raise RuntimeError(
            "GYM_SANDBOX_OPENSANDBOX_ENABLED is set but "
            "GYM_SANDBOX_OPENSANDBOX_ENV_FILE is not - point it at "
            "examples/gym-sandbox-opensandbox/targets/*.env."
        )
    lifecycle = build_gym_runner_lifecycle(
        GymRunnerConfig(
            backend_name=GymSandboxOpenSandboxBackend.name,
            mode=settings.gym_runner_mode,
            image=settings.gym_runner_image,
            env_file=settings.gym_sandbox_opensandbox_env_file,
            work_dir=settings.gym_sandbox_opensandbox_work_dir,
            work_volume=settings.gym_sandbox_opensandbox_docker_volume,
            host_env_file=settings.gym_sandbox_opensandbox_host_env_file,
            gym_dir=settings.gym_dir,
        )
    )
    return GymSandboxOpenSandboxBackend(
        submitter=lifecycle.submitter,
        status_reader=lifecycle.status_reader,
        terminator=lifecycle.terminator,
    )
