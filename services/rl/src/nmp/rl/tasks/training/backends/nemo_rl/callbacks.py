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

    ``train_loss`` and ``val_loss`` are accumulated as time-series lists and resent
    under a ``metrics`` key on every update, matching
    ``nmp.customization_common.training.callbacks.TrainingProgressCallback``. This
    is what makes a loss curve recoverable at all: ``report_running`` REPLACES the
    task's ``status_details`` blob, so a report carrying only the current step
    leaves no history behind. Studio reads exactly this shape
    (``CustomizationMetricValue[]``).

    Only these two series accumulate. The wider RL metric set rides along as
    current-step scalars, because every series is resent in full on every update
    and the payload grows with the product of series count and step count.
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
        self._reporter.report_running(
            phase="training",
            step=0,
            max_steps=max_steps,
            num_epochs=num_epochs,
            metrics=self._build_metrics_summary(),
        )

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
            **additional_metrics: Additional training metrics to report as current-step
                scalars — DPO's preference_loss/rewards_rejected_mean, GRPO's
                reward/advantages/kl_penalty, or the shared token counts. These are
                not accumulated into the series; see the class docstring.
        """
        self._train_metrics.append({"step": step, "epoch": epoch, "value": loss})
        self._reporter.report_running(
            phase="training",
            step=step,
            epoch=epoch,
            train_loss=loss,
            lr=lr,
            grad_norm=grad_norm,
            metrics=self._build_metrics_summary(),
            **additional_metrics,
        )

    def report_validation(
        self,
        step: int,
        epoch: int,
        val_loss: float | None = None,
        **additional_metrics: Any,
    ) -> None:
        """Report validation results.

        Args:
            step: Training step number
            epoch: Current epoch number
            val_loss: Validation loss value, or None for algorithms that do not
                produce one. GRPO validates on ``accuracy``/``avg_length`` and
                reports no loss at all, so the key is omitted rather than sent as
                null and charted as zero.
            **additional_metrics: Additional validation metrics to report (e.g., accuracy,
                num_valid_samples, or any other validation-specific metrics)
        """
        details: dict[str, Any] = {"step": step, "epoch": epoch}
        if val_loss is not None:
            self._val_metrics.append({"step": step, "epoch": epoch, "value": val_loss})
            details["val_loss"] = val_loss

        self._reporter.report_running(
            phase="validation",
            metrics=self._build_metrics_summary(),
            **details,
            **additional_metrics,
        )

    def report_checkpoint_saved(self, step: int, epoch: int, checkpoint_path: str | None = None) -> None:
        """Report that a checkpoint was saved."""
        self._reporter.report_running(
            phase="checkpoint_saved",
            step=step,
            epoch=epoch,
            checkpoint_path=checkpoint_path,
            metrics=self._build_metrics_summary(),
        )

    def close(self) -> None:
        """Clean up resources."""
        self._reporter.close()
