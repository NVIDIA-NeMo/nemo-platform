# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job context for unsloth container task entrypoints.

Mirror of :mod:`nmp.automodel.app.jobs.context`. Each service owns its
own context type so the task entrypoints stay decoupled — even though
the env-var shape is platform-wide.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from nmp.common.entities.constants import DEFAULT_WORKSPACE
from nmp.common.jobs.constants import (
    DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH,
    NEMO_JOB_ATTEMPT_ID_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_STEP_ENVVAR,
    NEMO_JOB_TASK_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.unsloth.app.constants import (
    DEFAULT_JOB_STORAGE_PATH,
    NMP_FILES_URL_ENVVAR,
    NMP_JOBS_URL_ENVVAR,
)

DEFAULT_JOB_ID = "unknown-job-id"
DEFAULT_ATTEMPT_ID = "attempt-0"
DEFAULT_STEP = "unknown-step"
DEFAULT_TASK = "unknown-task"


def _normalize_task_name(task: str) -> str:
    """Ensure task name uses the expected Jobs prefix.

    Generated tasks in k8s don't start with a lowercase letter per
    ``NAME_PATTERN``, so we normalize by adding ``task-`` when missing.
    Matches the Docker backend's ``task_id = f"task-{uuid.uuid4().hex}"``.
    """
    if task.startswith("task-"):
        return task
    return f"task-{task}"


@dataclass(frozen=True)
class NMPJobContext:
    """NeMo Platform Job context populated from Job Controller environment variables."""

    workspace: str
    job_id: str
    attempt_id: str
    step: str
    task: str

    jobs_url: str | None
    files_url: str | None

    storage_path: Path
    config_path: Path

    @property
    def normalized_task(self) -> str:
        """Task normalized for Jobs API compatibility."""
        return _normalize_task_name(self.task)

    @classmethod
    def from_env(cls) -> Self:
        """Create a :class:`NMPJobContext` from environment variables."""
        return cls(
            workspace=os.environ.get(NEMO_JOB_WORKSPACE_ENVVAR, DEFAULT_WORKSPACE),
            job_id=os.environ.get(NEMO_JOB_ID_ENVVAR, DEFAULT_JOB_ID),
            attempt_id=os.environ.get(NEMO_JOB_ATTEMPT_ID_ENVVAR, DEFAULT_ATTEMPT_ID),
            step=os.environ.get(NEMO_JOB_STEP_ENVVAR, DEFAULT_STEP),
            task=os.environ.get(NEMO_JOB_TASK_ENVVAR, DEFAULT_TASK),
            jobs_url=os.environ.get(NMP_JOBS_URL_ENVVAR),
            files_url=os.environ.get(NMP_FILES_URL_ENVVAR),
            storage_path=Path(os.environ.get(PERSISTENT_JOB_STORAGE_PATH_ENVVAR, DEFAULT_JOB_STORAGE_PATH)),
            config_path=Path(
                os.environ.get(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH)
            ),
        )
