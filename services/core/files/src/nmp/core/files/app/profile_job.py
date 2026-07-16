# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compile and submit a job that profiles a fileset's contents.

The Files service does not profile datasets itself. This helper builds a
one-step CPU job whose container runs the dataset-profiler task
(``python -m nemo_datasets_plugin.tasks.profile``) over the fileset and
publishes the resulting ``DatasetProfile`` as a job result artifact named
``profile``. The profiler ships in the ``nemo-datasets`` plugin, which is baked
into the shared ``nmp-cpu-tasks`` image (and installed in the platform
virtualenv used by the local subprocess job backend); the Files service only
references it by task module name.
"""

from __future__ import annotations

import logging
import uuid

from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.jobs import (
    ContainerSpecParam,
    CPUExecutionProviderParam,
    PlatformJobResponse,
    PlatformJobSpecParam,
    PlatformJobStepSpecParam,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus

logger = logging.getLogger(__name__)

_PROFILE_TASK_IMAGE = "nmp-cpu-tasks"
_PROFILE_TASK_COMMAND = ["nemo_datasets_plugin.tasks.profile"]
_PROFILE_STEP_NAME = "profile"
_PROFILE_JOB_SOURCE = "files"
_TERMINAL_JOB_STATES = frozenset(status.value for status in PlatformJobStatus.terminals())


def _job_targets_fileset(job: PlatformJobResponse, fileset_name: str) -> bool:
    spec = job.spec or {}
    return isinstance(spec, dict) and spec.get("fileset") == fileset_name


def _is_active(job: PlatformJobResponse) -> bool:
    """True when the job's status is not one of the terminal states.

    ``job.status`` is a plain lowercase string from the SDK today. ``getattr(_, "value", _)``
    also unwraps a ``PlatformJobStatus`` enum, so if the SDK ever emits one this keeps matching
    the lowercase terminal values instead of degrading to ``"platformjobstatus.completed"``.
    """
    status = getattr(job.status, "value", job.status)
    return str(status).lower() not in _TERMINAL_JOB_STATES


async def find_active_profile_job(
    sdk: AsyncNeMoPlatform,
    *,
    workspace: str,
    fileset_name: str,
) -> PlatformJobResponse | None:
    """Return an in-flight profiling job for ``fileset_name``, or None.

    The Jobs service is the source of truth for job state; profiling jobs are tagged with
    ``source="files"`` and ``spec={"fileset": ...}``, so we query it directly rather than
    persisting a job pointer on the fileset. We filter by ``source`` server-side and test
    terminality in memory over a single ``sdk.jobs.list`` scan.

    We deliberately do not narrow by status server-side: filtering by a *set* of non-terminal
    statuses did not match reliably in practice (an earlier attempt returned nothing and broke
    dedup). The trade-off is scanning every ``source="files"`` job for the workspace — fine at
    current volumes; revisit with a verified server-side status filter if that history grows.
    """
    async for job in sdk.jobs.list(workspace=workspace, filter={"source": _PROFILE_JOB_SOURCE}):
        if _job_targets_fileset(job, fileset_name) and _is_active(job):
            return job
    return None


def _build_platform_spec(workspace: str, fileset_name: str) -> PlatformJobSpecParam:
    """Build the platform job spec for profiling ``workspace/fileset_name``."""
    return PlatformJobSpecParam(
        steps=[
            PlatformJobStepSpecParam(
                name=_PROFILE_STEP_NAME,
                executor=CPUExecutionProviderParam(
                    provider="cpu",
                    profile="default",
                    container=ContainerSpecParam(
                        image=get_qualified_image(_PROFILE_TASK_IMAGE),
                        entrypoint=["python", "-m"],
                        command=list(_PROFILE_TASK_COMMAND),
                    ),
                ),
                config={"workspace": workspace, "fileset": fileset_name},
            )
        ],
    )


async def submit_profile_job(
    sdk: AsyncNeMoPlatform,
    *,
    workspace: str,
    fileset_name: str,
) -> PlatformJobResponse:
    """Submit a profiling job for ``workspace/fileset_name`` and return it."""
    job_name = f"profile-{fileset_name}-{uuid.uuid4().hex[:8]}"
    platform_spec = _build_platform_spec(workspace, fileset_name)
    logger.info("Submitting profile job %s for fileset %s/%s", job_name, workspace, fileset_name)
    return await sdk.jobs.create(
        source=_PROFILE_JOB_SOURCE,
        spec={"fileset": fileset_name},
        platform_spec=platform_spec,
        workspace=workspace,
        name=job_name,
    )
