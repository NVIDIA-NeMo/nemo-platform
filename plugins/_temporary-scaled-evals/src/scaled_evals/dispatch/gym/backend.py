# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared runner lifecycle construction for Gym-backed providers."""

from __future__ import annotations

from dataclasses import dataclass

from scaled_evals.dispatch.gym.docker import (
    make_gym_docker_status_reader,
    make_gym_docker_submitter,
    make_gym_docker_terminator,
)
from scaled_evals.dispatch.gym.process import (
    make_gym_process_status_reader,
    make_gym_process_submitter,
    make_gym_process_terminator,
)
from scaled_evals.dispatch.runtime_backend import StatusReader, Submitter, Terminator


@dataclass(frozen=True)
class GymRunnerConfig:
    """Explicit execution settings for one Gym backend.

    Provider modules remain responsible for enablement and settings validation.
    This value only normalizes construction of the matching submitter, status
    reader, and terminator.
    """

    backend_name: str
    mode: str
    env_file: str
    work_dir: str
    image: str | None = None
    work_volume: str | None = None
    host_env_file: str | None = None
    gym_dir: str | None = None


@dataclass(frozen=True)
class GymRunnerLifecycle:
    submitter: Submitter
    status_reader: StatusReader
    terminator: Terminator


def build_gym_runner_lifecycle(config: GymRunnerConfig) -> GymRunnerLifecycle:
    """Build one Gym execution lifecycle without choosing provider policy."""
    if config.mode == "process":
        if not config.gym_dir:
            raise RuntimeError("Gym process mode requires GYM_DIR")
        return GymRunnerLifecycle(
            submitter=make_gym_process_submitter(
                backend_name=config.backend_name,
                gym_dir=config.gym_dir,
                env_file=config.env_file,
                work_dir=config.work_dir,
            ),
            status_reader=make_gym_process_status_reader(work_dir=config.work_dir),
            terminator=make_gym_process_terminator(),
        )
    if config.mode != "docker":
        raise RuntimeError(f"unsupported Gym runner mode: {config.mode}")
    if not config.work_volume:
        raise RuntimeError("Gym docker mode requires a work volume")
    return GymRunnerLifecycle(
        submitter=make_gym_docker_submitter(
            backend_name=config.backend_name,
            image=config.image,
            env_file=config.env_file,
            work_dir=config.work_dir,
            work_volume=config.work_volume,
            host_env_file=config.host_env_file,
        ),
        status_reader=make_gym_docker_status_reader(work_dir=config.work_dir),
        terminator=make_gym_docker_terminator(),
    )
