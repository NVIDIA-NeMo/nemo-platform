# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Progress reporting for training tasks.

This module provides progress reporting to the Jobs service using
the NeMo Platform SDK. The `JobsServiceProgressReporter` class
handles high-level phase reporting for the training runner.

For training-specific metrics (loss, validation, checkpoints), see
the `TrainingProgressCallback` in the automodel backend which composes
this reporter and provides training-specific methods.
"""

import logging
import os
from typing import Any

from nmp.automodel.app.constants import SERVICE_NAME
from nmp.automodel.app.jobs.context import NMPJobContext
from nmp.common.sdk_factory import get_task_sdk

logger = logging.getLogger(__name__)


class JobsServiceProgressReporter:
    """Reports high-level progress to the Jobs service.

    This class provides progress reporting for the training runner:
    - configure_progress_tracking(max_steps, num_epochs) - Set bounds for percentage calculation
    - report_running(phase, **details) - Report current phase (auto-calculates percentage_done)
    - report_completed(message) - Report successful completion
    - report_error(message) - Report failure

    For training backends that need to report detailed metrics, the
    `update_task` method is exposed for direct use. See `TrainingProgressCallback`
    in the automodel backend for an example.
    """

    def __init__(self, job_ctx: NMPJobContext):
        """Initialize the progress reporter."""
        self._job_ctx = job_ctx
        self._sdk = get_task_sdk(SERVICE_NAME)
        self._is_main_rank = int(os.environ.get("RANK", "0")) == 0
        self._max_steps = 0
        self._num_epochs = 0

        self._enabled = self._is_main_rank and all(
            [self._job_ctx.job_id, self._job_ctx.step, self._job_ctx.normalized_task]
        )

    def configure_progress_tracking(self, max_steps: int, num_epochs: int) -> None:
        """Configure progress tracking at the start of training.

        Args:
            max_steps: Total number of training steps
            num_epochs: Total number of epochs
        """
        self._max_steps = max_steps
        self._num_epochs = num_epochs

    def _calculate_percentage_done(self, step: int | None) -> int:
        """Calculate percentage done based on current step and max_steps."""
        if step is None or self._max_steps <= 0:
            return 0
        return int((step / self._max_steps) * 100)

    def update_task(
        self,
        status: str = "active",
        status_details: dict[str, Any] | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Update task status via SDK.

        This is the low-level method exposed for composition by training
        callbacks that need to report detailed metrics.

        Args:
            status: Task status ("active", "completed", "error")
            status_details: Details about the current status
            error_details: Error information (for status="error")
        """
        if not self._enabled:
            return

        # Only report from rank 0 in distributed training
        if not self._is_main_rank:
            return

        try:
            self._sdk.jobs.tasks.create_or_update(
                name=self._job_ctx.normalized_task,
                workspace=self._job_ctx.workspace,
                job=self._job_ctx.job_id,
                step=self._job_ctx.step,
                status=status,
                status_details=status_details or {},
                error_details=error_details or {},
            )
        except Exception as e:
            logger.warning(f"Failed to update task progress: {e}")

    def fetch_current_metrics(self) -> dict[str, list[dict[str, float | int]]]:
        """Fetch accumulated metrics from the server for the current task.

        Used to seed metric accumulators on startup so that metrics
        survive pause/resume cycles. Returns empty lists on failure
        or if no prior metrics exist.
        """
        if not self._enabled:
            return {"train_loss": [], "val_loss": []}

        try:
            task = self._sdk.jobs.tasks.retrieve(
                name=self._job_ctx.normalized_task,
                workspace=self._job_ctx.workspace,
                job=self._job_ctx.job_id,
                step=self._job_ctx.step,
            )
            metrics = (task.status_details or {}).get("metrics", {})
            return {
                "train_loss": metrics.get("train_loss", []),
                "val_loss": metrics.get("val_loss", []),
            }
        except Exception as e:
            logger.info(f"No prior metrics to seed (expected on first run): {e}")
            return {"train_loss": [], "val_loss": []}

    # --- High-level runner methods ---

    def report_running(self, phase: str, **details: Any) -> None:
        """Report that a phase is running.

        If 'step' is provided and training schedule is set (via configure_progress_tracking),
        percentage_done is automatically calculated unless explicitly provided.

        Args:
            phase: The current phase (e.g., "compiling_config", "training")
            **details: Additional context (e.g., step, epoch, loss, backend="automodel")
        """
        # Auto-calculate percentage_done if step is provided and not already set
        if "step" in details and "percentage_done" not in details and self._max_steps > 0:
            details["percentage_done"] = self._calculate_percentage_done(details["step"])

        status_details = {"phase": phase, **details}
        self.update_task(status="active", status_details=status_details)

    def report_completed(self, message: str = "Completed") -> None:
        """Report task completed successfully.

        Args:
            message: Completion message
        """
        self.update_task(status="completed", status_details={"message": message, "phase": "completed"})

    def report_error(self, error: str | dict[str, Any]) -> None:
        """Report task error.

        Args:
            error: Error message (str) or error details dict with 'message', 'type', 'detail' keys.
                   The dict format is typically from create_error_details() in the errors module.
        """
        if isinstance(error, str):
            error_details = {"message": error}
        else:
            error_details = error
        self.update_task(status="error", error_details=error_details)

    def close(self) -> None:
        """Clean up SDK resources."""
        self._sdk.close()
