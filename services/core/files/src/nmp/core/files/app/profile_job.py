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

logger = logging.getLogger(__name__)

_PROFILE_TASK_IMAGE = "nmp-cpu-tasks"
_PROFILE_TASK_COMMAND = ["nemo_datasets_plugin.tasks.profile"]
_PROFILE_STEP_NAME = "profile"
_PROFILE_JOB_SOURCE = "files"


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
