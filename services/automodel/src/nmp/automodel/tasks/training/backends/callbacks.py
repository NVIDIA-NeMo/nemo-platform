# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging

from nmp.automodel.tasks.training.progress import JobsServiceProgressReporter

logger = logging.getLogger(__name__)


class TrainingProgressCallback:
    """
    Callback for reporting Automodel training progress to the Jobs service.

    This class composes JobsServiceProgressReporter and provides training-specific
    methods for reporting detailed metrics during training.

    Metric accumulation: train_loss and val_loss are accumulated as time-series
    lists and included in every status_details update under a ``metrics`` key,
    enabling loss-curve reconstruction from job status.
    """

    def __init__(self, reporter: JobsServiceProgressReporter):
        self._reporter = reporter

        prior = reporter.fetch_current_metrics()
        self._train_metrics: list[dict[str, float | int]] = prior.get("train_loss", [])
        self._val_metrics: list[dict[str, float | int]] = prior.get("val_loss", [])
        if self._train_metrics or self._val_metrics:
            logger.info(
                "Seeded metrics from server: %d train_loss, %d val_loss entries",
                len(self._train_metrics),
                len(self._val_metrics),
            )

    def _build_metrics_summary(self) -> dict[str, list[dict[str, float | int]]]:
        """Build the accumulated metrics payload for inclusion in status_details."""
        return {
            "train_loss": list(self._train_metrics),
            "val_loss": list(self._val_metrics),
        }

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
    ) -> None:
        """Report training step with metrics."""
        self._train_metrics.append({"step": step, "epoch": epoch, "value": loss})
        self._reporter.report_running(
            phase="training",
            step=step,
            epoch=epoch,
            train_loss=loss,
            lr=lr,
            grad_norm=grad_norm,
            metrics=self._build_metrics_summary(),
        )

    def report_validation(self, step: int, epoch: int, val_loss: float) -> None:
        """Report validation results."""
        self._val_metrics.append({"step": step, "epoch": epoch, "value": val_loss})
        self._reporter.report_running(
            phase="validation",
            step=step,
            epoch=epoch,
            val_loss=val_loss,
            metrics=self._build_metrics_summary(),
        )

    def report_checkpoint_saved(self, step: int, epoch: int, checkpoint_path: str | None = None) -> None:
        """Report that a checkpoint was saved."""
        self._reporter.report_running(
            phase="checkpoint_saved",
            step=step,
            epoch=epoch,
            checkpoint_path=checkpoint_path,
        )

    def report_epoch_end(self, step: int, epoch: int) -> None:
        """Report that an epoch has completed."""
        self._reporter.report_running(phase="epoch_end", step=step, epoch=epoch)

    def close(self) -> None:
        """Clean up resources."""
        self._reporter.close()
