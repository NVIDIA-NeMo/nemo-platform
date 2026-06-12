# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level progress reporting for training tasks.

Provides progress reporting to the Jobs service using the NeMo Platform SDK.
``JobsServiceProgressReporter`` handles high-level phase reporting for the
training runner; backends subclass it (or instantiate it directly) supplying
their own ``service_name`` so the task SDK resolves the right credentials.

For training-specific metrics (loss, validation, checkpoints) see the
``TrainingProgressCallback`` which composes this reporter.
"""

import logging
import os
from typing import Any, cast

from nmp.common.sdk_factory import get_task_sdk
from nmp.customization_common.service.context import NMPJobContext

logger = logging.getLogger(__name__)


class JobsServiceProgressReporter:
    """Reports high-level progress to the Jobs service."""

    def __init__(self, job_ctx: NMPJobContext, service_name: str):
        self._job_ctx = job_ctx
        self._sdk = get_task_sdk(service_name)
        self._is_main_rank = int(os.environ.get("RANK", "0")) == 0
        self._max_steps = 0
        self._num_epochs = 0

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

        try:
            self._sdk.jobs.tasks.create_or_update(
                name=self._job_ctx.normalized_task,
                workspace=self._job_ctx.workspace,
                job=self._job_ctx.job_id,
                step=self._job_ctx.step,
                status=status,  # ty: ignore[invalid-argument-type]
                status_details=status_details or {},
                error_details=error_details or {},
            )
        except Exception as e:
            logger.warning(f"Failed to update task progress: {e}")

    def fetch_current_metrics(self) -> dict[str, list[dict[str, float | int]]]:
        if not self._enabled:
            return {"train_loss": [], "val_loss": []}

        try:
            task = self._sdk.jobs.tasks.retrieve(
                name=self._job_ctx.normalized_task,
                workspace=self._job_ctx.workspace,
                job=self._job_ctx.job_id,
                step=self._job_ctx.step,
            )
            metrics = cast(dict[str, Any], (task.status_details or {}).get("metrics", {}) or {})
            return {
                "train_loss": metrics.get("train_loss", []),
                "val_loss": metrics.get("val_loss", []),
            }
        except Exception as e:
            logger.info(f"No prior metrics to seed (expected on first run): {e}")
            return {"train_loss": [], "val_loss": []}

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
