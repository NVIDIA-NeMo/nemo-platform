# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Training progress callbacks for Unsloth Jobs-service reporting."""

import logging

from nmp.unsloth.tasks.training.progress import JobsServiceProgressReporter

logger = logging.getLogger(__name__)


class TrainingProgressCallback:
    """Report Unsloth training progress to the Jobs service.

    Metric accumulation matches Automodel: ``train_loss`` and ``val_loss``
    time series are included under ``metrics`` on every update.
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
        return {
            "train_loss": list(self._train_metrics),
            "val_loss": list(self._val_metrics),
        }

    def report_training_start(self, max_steps: int, num_epochs: int, *, backend: str = "unsloth") -> None:
        self._reporter.configure_progress_tracking(max_steps, num_epochs)
        self._reporter.report_running(
            phase="training",
            step=0,
            max_steps=max_steps,
            num_epochs=num_epochs,
            backend=backend,
        )

    def report_train_step(
        self,
        step: int,
        epoch: int,
        loss: float,
        lr: float | None = None,
        grad_norm: float | None = None,
        *,
        backend: str = "unsloth",
    ) -> None:
        self._train_metrics.append({"step": step, "epoch": epoch, "value": loss})
        self._reporter.report_running(
            phase="training",
            step=step,
            epoch=epoch,
            train_loss=loss,
            lr=lr,
            grad_norm=grad_norm,
            backend=backend,
            metrics=self._build_metrics_summary(),
        )

    def report_validation(
        self,
        step: int,
        epoch: int,
        val_loss: float,
        *,
        backend: str = "unsloth",
    ) -> None:
        self._val_metrics.append({"step": step, "epoch": epoch, "value": val_loss})
        self._reporter.report_running(
            phase="validation",
            step=step,
            epoch=epoch,
            val_loss=val_loss,
            backend=backend,
            metrics=self._build_metrics_summary(),
        )

    def report_checkpoint_saved(
        self,
        step: int,
        epoch: int,
        checkpoint_path: str | None = None,
        *,
        backend: str = "unsloth",
    ) -> None:
        self._reporter.report_running(
            phase="checkpoint_saved",
            step=step,
            epoch=epoch,
            checkpoint_path=checkpoint_path,
            backend=backend,
        )

    def report_epoch_end(self, step: int, epoch: int, *, backend: str = "unsloth") -> None:
        self._reporter.report_running(phase="epoch_end", step=step, epoch=epoch, backend=backend)

    def close(self) -> None:
        self._reporter.close()
