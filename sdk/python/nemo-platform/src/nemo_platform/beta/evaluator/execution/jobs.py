# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job-handle contract for evaluator backends that execute somewhere else.

A backend that runs work remotely hands back a handle rather than a result, so the caller decides
when to wait and can reach partial state, artifacts, and the job's own identity in the meantime.
:class:`~nemo_platform.beta.evaluator.execution.evaluator.Evaluator` waits on the caller's behalf, so the
convenience API still returns a finished result either way.

In-process execution uses :class:`LocalJob`, which holds a task that is already running. Creating
the job starts the work, exactly as creating a platform job does; waiting collects it. A caller
that starts several evaluations and then waits on them therefore gets the same concurrency either
way, which neither running the work eagerly inside ``evaluate`` nor deferring it to the wait would
give: both leave the evaluations to happen one after another.
"""

from __future__ import annotations

import asyncio
import math
from typing import Generic, Protocol, TypeVar, runtime_checkable

#: Declared with ``TypeVar`` rather than PEP 695 syntax: this package supports Python 3.11,
#: where ``class Job[T]`` is a syntax error.
ResultT = TypeVar("ResultT")

#: Default poll cadence, matching the evaluator plugin's dataset job resources.
DEFAULT_POLL_INTERVAL_SECONDS = 10.0

#: Default ceiling on a whole run.
DEFAULT_JOB_TIMEOUT_SECONDS = 3600.0

#: Default ceiling on time spent before a job starts running.
DEFAULT_PENDING_TIMEOUT_SECONDS = 600.0


@runtime_checkable
class EvaluationJob(Protocol[ResultT]):
    """An in-flight evaluation, awaited through its own methods.

    Implementations may accept extra keyword arguments with defaults without breaking conformance,
    which is how a handle can also expose artifacts, status, or a job name that this contract does
    not name.

    ``isinstance`` against this protocol tests member *presence* only. It cannot tell this apart
    from :class:`SyncEvaluationJob`, whose members have identical names — use
    :func:`inspect.iscoroutinefunction` for that, as
    :mod:`nemo_platform.beta.evaluator.execution.evaluator` does for the backend contracts.
    """

    async def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Wait until the job reaches a terminal status.

        Args:
            poll_interval_seconds: Delay between status checks.
            job_timeout_seconds: Ceiling on the whole run.
            pending_timeout_seconds: Ceiling on time spent before the job starts running.

        Raises:
            RuntimeError: If the job reaches a terminal failure status.
            TimeoutError: If polling exceeds a configured timeout.
        """
        ...

    async def get_result(self) -> ResultT:
        """Return the finished result.

        Call after :meth:`wait_until_done`; a job that has not finished has no result to give.
        """
        ...


@runtime_checkable
class SyncEvaluationJob(Protocol[ResultT]):
    """The sync counterpart of :class:`EvaluationJob`."""

    def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Wait until the job reaches a terminal status.

        See :meth:`EvaluationJob.wait_until_done`.
        """
        ...

    def get_result(self) -> ResultT:
        """Return the finished result.

        See :meth:`EvaluationJob.get_result`.
        """
        ...


class LocalJob(Generic[ResultT]):
    """An evaluation already running in this process.

    Takes a started task, so the work is in flight by the time the handle exists — the state a
    platform job is in once it has been created. Waiting collects the task; the task itself is
    what makes a second wait return the first outcome rather than running anything again.

    ``poll_interval_seconds`` and ``pending_timeout_seconds`` are accepted and ignored: nothing
    polls and nothing queues. ``job_timeout_seconds`` is honoured, so the parameter means the same
    thing here as it does remotely; pass ``float("inf")`` for no ceiling.
    """

    def __init__(self, task: asyncio.Task[ResultT]) -> None:
        """Store the already-running task."""
        self._task = task

    async def wait_until_done(
        self,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
        pending_timeout_seconds: float = DEFAULT_PENDING_TIMEOUT_SECONDS,
    ) -> None:
        """Wait for the running evaluation to finish.

        The task is shielded, so exceeding ``job_timeout_seconds`` means this call gave up
        waiting, not that the evaluation was cancelled — the same thing a timeout means against a
        backend running the work elsewhere. A later wait can still collect it.
        """
        del poll_interval_seconds, pending_timeout_seconds
        timeout = None if math.isinf(job_timeout_seconds) else job_timeout_seconds
        await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)

    async def get_result(self) -> ResultT:
        """Return the result, or raise if the evaluation has not finished or did not succeed."""
        if not self._task.done():
            raise RuntimeError("evaluation has not finished yet; call wait_until_done() first")
        return self._task.result()
