# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level progress reporting for training tasks.

Provides progress reporting to the Jobs service using the NeMo Platform SDK.
``JobsServiceProgressReporter`` handles high-level phase reporting for the
training runner; backends subclass it (or instantiate it directly) supplying
their own ``service_name`` so the task SDK resolves the right credentials.

Every update REPLACES the task's ``status_details``, so a field is only as
durable as the next report that omits it. ``update_task`` carries a defined set
of fields across updates that don't restate them -- see :data:`_CARRY_FORWARD`.

For training-specific metrics (loss, validation, checkpoints) see the
``TrainingProgressCallback`` which composes this reporter.
"""

import logging
import os
from typing import Any, cast

from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.jobs.client import JobsClient
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from nemo_platform_plugin.jobs.types import PlatformJobTaskUpdate
from nmp.common.sdk_factory import get_task_sdk
from nmp.customization_common.service.context import NMPJobContext

logger = logging.getLogger(__name__)

#: Fields restated on updates that don't supply their own.
#:
#: The rule is *what stays true after the update that stated it*:
#:
#: - ``metrics`` is cumulative -- the whole point is that it grows.
#: - ``max_steps``/``num_epochs`` are run constants, and are only ever stated
#:   once, by ``report_training_start``.
#: - ``step``/``epoch`` are monotonic; a run does not un-reach step 30.
#: - ``checkpoint_path`` is a sticky latest-value, true until superseded.
#:
#: Deliberately excluded: ``phase`` (every report sets its own), and the
#: per-step observations (``train_loss``, ``lr``, ``grad_norm``, ``reward``,
#: ...). Those describe one instant, and a stale copy would misrepresent
#: "current" -- nothing is lost by letting them expire, because every one of
#: them is now recoverable from its series in ``metrics``.
#:
#: ``percentage_done`` is also excluded: it is derived from ``step`` and
#: ``max_steps``, both of which are carried, so a consumer can recompute it
#: rather than risk a copy that contradicts its own inputs.
_CARRY_FORWARD = frozenset({"metrics", "max_steps", "num_epochs", "step", "epoch", "checkpoint_path"})


def _carries_information(value: Any) -> bool:
    """Whether a stored value is worth restating on a later update.

    Empty containers are dropped so a task doesn't accumulate keys that say
    nothing -- notably the all-empty ``metrics`` dict a job reports before its
    first training step.
    """
    if value is None:
        return False
    if isinstance(value, dict):
        return any(_carries_information(item) for item in value.values())
    if isinstance(value, (list, str)):
        return bool(value)
    return True


class JobsServiceProgressReporter:
    """Reports high-level progress to the Jobs service."""

    def __init__(self, job_ctx: NMPJobContext, service_name: str):
        self._job_ctx = job_ctx
        self._sdk = get_task_sdk(service_name)
        self._is_main_rank = int(os.environ.get("RANK", "0")) == 0
        self._max_steps = 0
        self._num_epochs = 0

        #: Last-seen value of each :data:`_CARRY_FORWARD` field, populated as
        #: updates pass through and from the stored blob when one is read back.
        self._carried: dict[str, Any] = {}

        # Gate on real job context, not bare truthiness: from_env() fills missing
        # identifiers with non-empty sentinel defaults, which would otherwise
        # enable reporting (and failing SDK calls) outside a real job run.
        self._enabled = self._is_main_rank and self._job_ctx.is_configured

    def configure_progress_tracking(self, max_steps: int, num_epochs: int) -> None:
        """Configure progress tracking at the start of training."""
        self._max_steps = max_steps
        self._num_epochs = num_epochs

    def _calculate_percentage_done(self, step: int | None) -> int:
        if step is None or self._max_steps <= 0:
            return 0
        # Clamp to 100: step can exceed max_steps (e.g. resumed/over-run), and
        # downstream progress consumers expect a bounded percentage.
        return min(100, int((step / self._max_steps) * 100))

    def _carry_forward(self, status_details: dict[str, Any] | None) -> dict[str, Any]:
        """Restate the :data:`_CARRY_FORWARD` fields this update doesn't supply.

        ``status_details`` is REPLACED by the Jobs service, not merged, so a
        field survives only as long as every subsequent report repeats it. Three
        things were being lost to that:

        - the accumulated ``metrics``, on the runner's checkpoint/completion/
          failure reports -- so every job ended by erasing its own curves;
        - ``max_steps``/``num_epochs``, stated once at training start and gone
          from the first training step onward;
        - ``checkpoint_path``, published by one report and wiped by the next.

        Values are remembered as they pass through (write-through), so a process
        that has already stated a field can restate it for free. The stored blob
        is read back only when the update omits ``metrics``, which is the tell
        that it did not come from ``TrainingProgressCallback`` -- i.e. it is one
        of the handful the runner makes, from a different process that holds no
        state. Per-step training reports always carry ``metrics``, so the hot
        path never pays for a round-trip.
        """
        details = dict(status_details or {})
        self._remember(details)

        missing = [field for field in _CARRY_FORWARD if field not in details]
        if not missing:
            return details

        if "metrics" not in details:
            self._fetch_status_details()

        for field in missing:
            if field in self._carried:
                details[field] = self._carried[field]
        return details

    def update_task(
        self,
        status: str = "active",
        status_details: dict[str, Any] | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return

        if not self._is_main_rank:
            return

        details = self._carry_forward(status_details)

        try:
            jobs = client_from_platform(self._sdk, JobsClient)
            jobs.update_job_step_task(
                name=self._job_ctx.normalized_task,
                workspace=self._job_ctx.workspace,
                job=self._job_ctx.job_id,
                step=self._job_ctx.step,
                body=PlatformJobTaskUpdate(
                    status=PlatformJobStatus(status),
                    status_details=details,
                    error_details=error_details or {},
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to update task progress: {e}")

    def _fetch_status_details(self) -> dict[str, Any]:
        """Read back the task's stored ``status_details`` blob.

        Refreshes the carry-forward cache as a side effect, so that the
        resume-seeding fetch ``TrainingProgressCallback`` makes at construction
        doubles as the seed for :meth:`_carry_forward`. Without that, a resumed
        run would drop the previous run's ``checkpoint_path``: its first report
        already carries ``metrics``, so it would never read the blob back.
        """
        if not self._enabled:
            return {}

        try:
            jobs = client_from_platform(self._sdk, JobsClient)
            task = jobs.get_job_step_task(
                name=self._job_ctx.normalized_task,
                workspace=self._job_ctx.workspace,
                job=self._job_ctx.job_id,
                step=self._job_ctx.step,
            ).data()
            stored = cast(dict[str, Any], task.status_details or {})
        except Exception as e:
            # Expected on a first run, where the task has no stored details yet.
            # Serves both resume seeding and update_task's carry-forward, so the
            # message stays neutral about which caller hit it.
            logger.info(f"No stored status details available: {e}")
            return {}

        self._remember(stored)
        return stored

    def _remember(self, source: dict[str, Any]) -> None:
        """Cache the carry-forward fields present in ``source``."""
        self._carried.update(
            {field: value for field, value in source.items() if field in _CARRY_FORWARD and _carries_information(value)}
        )

    def fetch_current_metrics(self) -> dict[str, list[dict[str, float | int]]]:
        """Read back every stored metric series, for resume seeding.

        Deliberately not restricted to a known set of names: backends decide what
        they accumulate, and a resumed job that only seeded ``train_loss`` would
        silently restart every other curve from empty. Non-list values are
        dropped so a malformed blob cannot poison the accumulator.
        """
        metrics = cast(dict[str, Any], self._fetch_status_details().get("metrics", {}) or {})
        return {name: points for name, points in metrics.items() if isinstance(points, list)}

    def report_running(self, phase: str, **details: Any) -> None:
        if "step" in details and "percentage_done" not in details and self._max_steps > 0:
            details["percentage_done"] = self._calculate_percentage_done(details["step"])

        status_details = {"phase": phase, **details}
        self.update_task(status="active", status_details=status_details)

    def report_completed(self, message: str = "Completed") -> None:
        self.update_task(status="completed", status_details={"message": message, "phase": "completed"})

    def report_error(self, error: str | dict[str, Any]) -> None:
        error_details = {"message": error} if isinstance(error, str) else error
        self.update_task(status="error", error_details=error_details)

    def close(self) -> None:
        self._sdk.close()
