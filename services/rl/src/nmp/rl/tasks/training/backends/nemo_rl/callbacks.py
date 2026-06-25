# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import logging
from typing import Any

from nmp.customization_common.training.progress import JobsServiceProgressReporter

logger = logging.getLogger(__name__)


class TrainingProgressCallback:
    """
    Callback for reporting NeMo RL training progress to the Jobs service.

    This class composes JobsServiceProgressReporter and provides training-specific
    methods for reporting detailed metrics during training.
    """

    def __init__(self, reporter: JobsServiceProgressReporter):
        self._reporter = reporter

    def report_training_start(self, max_steps: int, num_epochs: int) -> None:
        """Report that training has started with schedule information."""
        self._reporter.configure_progress_tracking(max_steps, num_epochs)
        self._reporter.report_running(phase="training", step=0, max_steps=max_steps, num_epochs=num_epochs)

    def report_train_step(
        self,
        step: int,
        epoch: int,
        loss: float,
        lr: float | None = None,
        grad_norm: float | None = None,
        **additional_metrics: Any,
    ) -> None:
        """Report training step with metrics.

        Args:
            step: Training step number
            epoch: Current epoch number
            loss: Training loss value
            lr: Learning rate (optional)
            grad_norm: Gradient norm (optional)
            **additional_metrics: Additional training metrics to report (e.g., num_valid_samples,
                preference_loss, rewards_rejected_mean, global_valid_seqs, global_valid_toks)
        """
        self._reporter.report_running(
            phase="training",
            step=step,
            epoch=epoch,
            train_loss=loss,
            lr=lr,
            grad_norm=grad_norm,
            **additional_metrics,
        )

    def report_validation(
        self,
        step: int,
        epoch: int,
        val_loss: float,
        **additional_metrics: Any,
    ) -> None:
        """Report validation results.

        Args:
            step: Training step number
            epoch: Current epoch number
            val_loss: Validation loss value
            **additional_metrics: Additional validation metrics to report (e.g., accuracy,
                num_valid_samples, or any other validation-specific metrics)
        """
        self._reporter.report_running(
            phase="validation",
            step=step,
            epoch=epoch,
            val_loss=val_loss,
            **additional_metrics,
        )

    def report_checkpoint_saved(self, step: int, epoch: int, checkpoint_path: str | None = None) -> None:
        """Report that a checkpoint was saved."""
        self._reporter.report_running(phase="checkpoint_saved", step=step, epoch=epoch, checkpoint_path=checkpoint_path)

    def close(self) -> None:
        """Clean up resources."""
        self._reporter.close()
