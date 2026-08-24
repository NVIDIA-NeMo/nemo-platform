# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compile and submit a job that profiles a fileset's contents.

The Files service does not profile datasets itself. This helper builds a
one-step CPU job whose container runs the dataset-profiler task
(``python -m nemo_datasets_plugin.tasks.profile``) over the fileset. The task
writes the resulting ``DatasetProfile`` back through
``PUT .../filesets/{name}/profile`` and also publishes it as a job result
artifact named ``profile``. The profiler ships in the ``nemo-datasets`` plugin,
which is baked into the shared ``nmp-cpu-tasks`` image (and installed in the
platform virtualenv used by the local subprocess job backend); the Files service
only references it by task module name.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import NamedTuple

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

# Job statuses are classified by name rather than derived by subtracting the terminal ones, because
# the question that matters here is not "has it stopped?" but "will it produce a profile without
# further intervention?" — and the two answers differ for a paused job. Every status is assigned to
# exactly one set below; ``test_every_job_status_is_classified`` fails if the enum grows a member
# that nobody has thought about, rather than letting it silently default to "in flight".
_RUNNING_JOB_STATES = frozenset(
    status.value
    for status in (
        PlatformJobStatus.CREATED,
        PlatformJobStatus.PENDING,
        PlatformJobStatus.ACTIVE,
        PlatformJobStatus.CANCELLING,
        PlatformJobStatus.RESUMING,
    )
)
# A paused job is suspended indefinitely: it will produce nothing until someone resumes it, so it
# must not hold the dedup slot, or one pause would block profiling that fileset forever with no
# recourse through this API. It is still worth reporting — the caller can resume or cancel it.
_PAUSED_JOB_STATES = frozenset({PlatformJobStatus.PAUSED.value, PlatformJobStatus.PAUSING.value})
# Cancellation is kept apart from failure: it is a deliberate act with no error to investigate, and
# the remedy is simply to re-run. Folding it into "failed" makes a UI badge or an alert treat a
# user's own stop as a breakage.
_CANCELLED_JOB_STATES = frozenset({PlatformJobStatus.CANCELLED.value})
_FAILED_JOB_STATES = frozenset({PlatformJobStatus.ERROR.value})
_COMPLETED_JOB_STATES = frozenset({PlatformJobStatus.COMPLETED.value})


def job_status(job: PlatformJobResponse) -> str:
    """The job's status as the lowercase string the API reports.

    ``job.status`` is a plain lowercase string from the SDK today (``PlatformJobStatus`` is a
    ``Literal`` alias). Unwrapping ``.value`` first means that if the SDK ever emits a real enum
    this keeps producing ``"completed"`` rather than ``"platformjobstatus.completed"``.
    """
    return str(getattr(job.status, "value", job.status)).lower()


def _job_targets_fileset(job: PlatformJobResponse, fileset_name: str) -> bool:
    spec = job.spec or {}
    return isinstance(spec, dict) and spec.get("fileset") == fileset_name


def is_running_job(job: PlatformJobResponse) -> bool:
    """True while a job is in flight and will reach an outcome on its own."""
    return job_status(job) in _RUNNING_JOB_STATES


def is_paused_job(job: PlatformJobResponse) -> bool:
    """True when a job is suspended and needs a resume before it will do anything."""
    return job_status(job) in _PAUSED_JOB_STATES


def is_failed_job(job: PlatformJobResponse) -> bool:
    """True when a terminal job ended in error. Cancellation is :func:`is_cancelled_job`, not this."""
    return job_status(job) in _FAILED_JOB_STATES


def is_cancelled_job(job: PlatformJobResponse) -> bool:
    """True when a terminal job was cancelled rather than erroring or completing."""
    return job_status(job) in _CANCELLED_JOB_STATES


def _is_newer(job: PlatformJobResponse, other: PlatformJobResponse) -> bool:
    """True if ``job`` was created after ``other`` (a missing timestamp sorts oldest)."""
    if job.created_at is None:
        return False
    if other.created_at is None:
        return True
    return job.created_at > other.created_at


class ProfileJobLookup(NamedTuple):
    """The profiling jobs for a fileset that decide its state.

    ``running`` and ``paused`` are kept apart because only ``running`` will reach an outcome on its
    own: it is the one that suppresses a duplicate submission, while ``paused`` is reported but must
    not block a re-run.
    """

    running: PlatformJobResponse | None
    paused: PlatformJobResponse | None
    latest_terminal: PlatformJobResponse | None


async def scan_profile_jobs(
    sdk: AsyncNeMoPlatform,
    *,
    workspace: str,
    fileset_name: str,
) -> ProfileJobLookup:
    """Return the in-flight, paused, and most-recent-terminal profiling jobs for ``fileset_name``.

    The Jobs service is the source of truth for job state; profiling jobs are tagged with
    ``source="files"`` and ``spec={"fileset": ...}``, so we query it directly rather than
    persisting a job pointer on the fileset. We filter by ``source`` server-side and classify
    status in memory over a single ``sdk.jobs.list`` scan.

    We deliberately do not narrow by status server-side: filtering by a *set* of non-terminal
    statuses did not match reliably in practice (an earlier attempt returned nothing and broke
    dedup). The trade-off is scanning every ``source="files"`` job for the workspace — fine at
    current volumes; revisit with a verified server-side status filter if that history grows.
    """
    running: PlatformJobResponse | None = None
    paused: PlatformJobResponse | None = None
    latest_terminal: PlatformJobResponse | None = None
    async for job in sdk.jobs.list(workspace=workspace, filter={"source": _PROFILE_JOB_SOURCE}):
        if not _job_targets_fileset(job, fileset_name):
            continue
        if is_running_job(job):
            running = running or job
        elif is_paused_job(job):
            paused = paused or job
        elif latest_terminal is None or _is_newer(job, latest_terminal):
            latest_terminal = job
    return ProfileJobLookup(running=running, paused=paused, latest_terminal=latest_terminal)


async def find_running_profile_job(
    sdk: AsyncNeMoPlatform,
    *,
    workspace: str,
    fileset_name: str,
) -> PlatformJobResponse | None:
    """Return a profiling job for ``fileset_name`` that is already on its way, or None.

    A paused job is deliberately not returned: it would suppress the new submission and then never
    produce anything (see ``_PAUSED_JOB_STATES``).
    """
    return (await scan_profile_jobs(sdk, workspace=workspace, fileset_name=fileset_name)).running


def _build_platform_spec(workspace: str, fileset_name: str, row_budget: int | None) -> PlatformJobSpecParam:
    """Build the platform job spec for profiling ``workspace/fileset_name``.

    The config keys here are the task's input contract: it reads ``workspace``, ``fileset`` and
    ``row_budget`` off this dict and nothing else. A key spelled differently on the two sides is
    silently ignored rather than rejected -- which is exactly what happened when this wrote
    ``rows_per_file`` at a task reading ``row_budget``, so every budgeted request profiled
    uncapped. ``test_the_step_config_keys_are_the_ones_the_task_reads`` pins them together.
    """
    config: dict[str, object] = {"workspace": workspace, "fileset": fileset_name}
    # Left out entirely when unset, so the task applies the profiler's own default rather than
    # having this layer restate it.
    if row_budget is not None:
        config["row_budget"] = row_budget
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
                config=config,
            )
        ],
    )


def _job_name_for_fileset(fileset_name: str) -> str:
    """Build a valid, unique job name for profiling ``fileset_name``.

    Fileset names permit characters the Jobs name pattern forbids (uppercase, ``.``/``_``, ``--``
    runs, leading/trailing punctuation, over-length), so the fileset name is slugged into the
    readable middle of the job name while the ``profile-`` prefix and uuid suffix keep it valid and
    unique. A name with no alphanumerics slugs to empty and falls back to just prefix + suffix.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", fileset_name.lower()).strip("-")[:40].strip("-")
    suffix = uuid.uuid4().hex[:8]
    return f"profile-{slug}-{suffix}" if slug else f"profile-{suffix}"


async def submit_profile_job(
    sdk: AsyncNeMoPlatform,
    *,
    workspace: str,
    fileset_name: str,
    row_budget: int | None = None,
) -> PlatformJobResponse:
    """Submit a profiling job for ``workspace/fileset_name`` and return it."""
    job_name = _job_name_for_fileset(fileset_name)
    platform_spec = _build_platform_spec(workspace, fileset_name, row_budget)
    logger.info("Submitting profile job %s for fileset %s/%s", job_name, workspace, fileset_name)
    return await sdk.jobs.create(
        source=_PROFILE_JOB_SOURCE,
        spec={"fileset": fileset_name},
        platform_spec=platform_spec,
        workspace=workspace,
        name=job_name,
    )
