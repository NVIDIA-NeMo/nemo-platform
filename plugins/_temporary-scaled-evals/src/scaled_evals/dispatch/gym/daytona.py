# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The gym_daytona backend: Harbor-through-NeMo-Gym on Daytona sandboxes.

This module drives NeMo Gym's ``harbor_agent`` with
``harbor_environment_type: "daytona"`` (Harbor's built-in Daytona environment).

The ``sandbox_k8s`` path is unchanged — this is a second ``runtime`` value
(``gym_daytona``) selected by configuration, not a replacement for Harbor on
remote Kubernetes.

For the ``nemo_gym.sandbox`` API path (Mini SWE Agent 2), see
:mod:`scaled_evals.dispatch.gym.sandbox_daytona`.

Disabled by default (``GYM_DAYTONA_ENABLED=false``): ``launch`` raises and the
run is marked failed, same as ``sandbox_k8s``.
"""

from __future__ import annotations

from collections.abc import Callable

from scaled_evals.api.settings import settings
from scaled_evals.dispatch.gym.backend import GymRunnerConfig, build_gym_runner_lifecycle
from scaled_evals.dispatch.gym.common import build_gym_argv, make_gym_submitter
from scaled_evals.dispatch.runtime_backend import (
    CallableRuntimeBackend,
    LaunchHandle,
    LaunchSpec,
    RuntimeStatus,
)
from scaled_evals.dispatch.sandbox_k8s import Runner, summarize_harbor_result

# Re-export for tests and harness scripts.
__all__ = [
    "GymDaytonaBackend",
    "build_backend",
    "build_gym_argv",
    "make_gym_daytona_submitter",
]


class GymDaytonaBackend(CallableRuntimeBackend):
    """Backend for Harbor-through-NeMo-Gym on Daytona sandboxes."""

    name = "gym_daytona"

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
                "gym_daytona live submission is not wired; inject a submitter "
                "(integration point with the NeMo Gym harbor_agent + Daytona path)"
            ),
        )


def _harbor_jobs_override(spec: LaunchSpec, target_env: dict[str, str]) -> list[str]:
    if jobs_dir := target_env.get("GYM_HARBOR_JOBS_DIR"):
        return [f"++harbor_agent.responses_api_agents.harbor_agent.harbor_jobs_dir={jobs_dir}/{spec.evaluation_id}"]
    return []


def make_gym_daytona_submitter(
    *,
    gym_dir: str,
    env_file: str,
    work_dir: str = "/tmp",
    runner: Runner | None = None,
) -> Callable[[LaunchSpec], LaunchHandle]:
    """Build the live submitter that :meth:`GymDaytonaBackend.launch` calls."""
    return make_gym_submitter(
        backend_name=GymDaytonaBackend.name,
        gym_dir=gym_dir,
        env_file=env_file,
        work_dir=work_dir,
        runner=runner,
        extra_overrides_for_spec=_harbor_jobs_override,
    )


def build_backend() -> GymDaytonaBackend:
    """Construct the gym_daytona backend per settings."""
    if not settings.gym_daytona_enabled:
        return GymDaytonaBackend()
    if not settings.gym_daytona_env_file:
        raise RuntimeError(
            "GYM_DAYTONA_ENABLED is set but GYM_DAYTONA_ENV_FILE is "
            "not — point it at examples/gym-daytona/targets/*.env."
        )
    lifecycle = build_gym_runner_lifecycle(
        GymRunnerConfig(
            backend_name=GymDaytonaBackend.name,
            mode="docker",
            image=settings.gym_runner_image,
            env_file=settings.gym_daytona_env_file,
            work_dir=settings.gym_daytona_work_dir,
            work_volume=settings.gym_daytona_docker_volume,
            host_env_file=settings.gym_daytona_host_env_file,
        )
    )
    return GymDaytonaBackend(
        submitter=lifecycle.submitter,
        status_reader=lifecycle.status_reader,
        terminator=lifecycle.terminator,
    )
