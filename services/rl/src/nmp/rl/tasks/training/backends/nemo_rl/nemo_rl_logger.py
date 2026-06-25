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
import math
from typing import Any, Mapping, Optional

from nemo_rl.utils.logger import LoggerInterface
from nmp.customization_common.service.context import NMPJobContext
from nmp.customization_common.training.progress import JobsServiceProgressReporter
from nmp.rl.app.constants import SERVICE_NAME
from nmp.rl.tasks.training.backends.nemo_rl.callbacks import TrainingProgressCallback

_logger = logging.getLogger(__name__)


def has_metric_value(metric: Any) -> bool:
    """Check if a metric has a valid value."""
    if metric is not None and not math.isnan(metric):
        return True
    return False


class NemoRLLogger(LoggerInterface):
    """
    NemoRLLogger is a logger implementation that reports training updates to Jobs Service.

    It implements the LoggerInterface from nemo_rl.utils.logger to provide a consistent
    logging interface while maintaining compatibility with the Jobs Service.

    This implementation uses TrainingProgressCallback with JobsServiceProgressReporter
    to report progress via the NeMo Platform SDK.
    """

    def __init__(
        self,
        steps_per_epoch: int,
        job_ctx: NMPJobContext | None = None,
        log_interval: int = 10,
        max_steps: int | None = None,
        num_epochs: int | None = None,
    ):
        """Initialize the NemoRL logger.

        Args:
            steps_per_epoch: Number of steps per epoch (required for accurate epoch calculation).
            job_ctx: NeMo Platform job context for progress reporting (defaults to environment variables).
            log_interval: Number of steps between progress updates.
            max_steps: Total number of training steps (optional, used for progress reporting).
            num_epochs: Total number of epochs (optional, used for progress reporting).

        Raises:
            ValueError: If ``steps_per_epoch`` or ``log_interval`` is < 1. Both are
                used as divisors/moduli in ``log_metrics`` (epoch derivation and
                log-interval throttling), so non-positive values are rejected up
                front to fail fast instead of raising ZeroDivisionError mid-training.
        """
        if steps_per_epoch < 1:
            raise ValueError(f"steps_per_epoch must be >= 1, got {steps_per_epoch}")
        if log_interval < 1:
            raise ValueError(f"log_interval must be >= 1, got {log_interval}")

        self._job_ctx = job_ctx or NMPJobContext.from_env()
        self._log_interval = log_interval
        self._max_steps = max_steps
        self._num_epochs = num_epochs
        self._steps_per_epoch = steps_per_epoch

        # Create the callback for progress reporting
        self._reporter = JobsServiceProgressReporter(self._job_ctx, SERVICE_NAME)
        self._callback = TrainingProgressCallback(self._reporter)

        # Track best metrics for monitoring
        self._best_metric_value = float("inf")
        self._best_epoch: int | None = None
        self._closed = False

        _logger.info(
            f"Initialized NemoRLLogger with jobs_url={self._job_ctx.jobs_url}, "
            f"log_interval={log_interval}, max_steps={max_steps}, num_epochs={num_epochs}, "
            f"steps_per_epoch={steps_per_epoch}"
        )

    def log_metrics(
        self,
        metrics: dict[str, Any],
        step: int,
        prefix: Optional[str] = "",
        step_metric: Optional[str] = None,
        step_finished: bool = False,
    ) -> None:
        """Log metrics to NeMo Customizer.

        Args:
            metrics: Dict of metrics to log
            step: Global step value
            prefix: Optional prefix for metric names (e.g. "train", "validation", "timing/train")
            step_metric: Optional step metric name (ignored in this implementation)
            step_finished: Whether the step is finished (part of NeMo-RL's LoggerInterface; ignored here)
        """
        step = step + 1  # Increment step since we start counting from 1

        # Calculate epoch from step (epochs start from 1)
        epoch = ((step - 1) // self._steps_per_epoch) + 1

        # Handle training loss
        if prefix == "train" and has_metric_value(metrics.get("loss")):
            # Only report at log_interval to reduce output
            if step % self._log_interval == 0:
                # Extract core metrics
                loss = metrics["loss"]
                lr = metrics.get("lr")
                grad_norm = metrics.get("grad_norm")

                # Extract additional training metrics (whitelisted only)
                additional_metrics = {}
                for key in [
                    "num_valid_samples",
                    "preference_loss",
                    "rewards_rejected_mean",
                    "global_valid_seqs",
                    "global_valid_toks",
                ]:
                    if has_metric_value(metrics.get(key)):
                        additional_metrics[key] = metrics[key]

                self._callback.report_train_step(
                    step=step,
                    epoch=epoch,
                    loss=loss,
                    lr=lr,
                    grad_norm=grad_norm,
                    **additional_metrics,
                )

        # Handle validation metrics
        elif prefix and prefix.startswith("validation"):
            if has_metric_value(metrics.get("loss")):
                val_loss = metrics["loss"]

                # Extract additional validation metrics (whitelisted only)
                additional_metrics = {}
                for key in [
                    "num_valid_samples",
                    "preference_loss",
                    "rewards_rejected_mean",
                    "global_valid_seqs",
                    "global_valid_toks",
                ]:
                    if has_metric_value(metrics.get(key)):
                        additional_metrics[key] = metrics[key]

                self._callback.report_validation(
                    step=step,
                    epoch=epoch,
                    val_loss=val_loss,
                    **additional_metrics,
                )
                # Track best validation loss
                if val_loss < self._best_metric_value:
                    self._best_metric_value = val_loss
                    self._best_epoch = epoch

        _logger.debug(f"log_metrics: step={step}, prefix={prefix}, metrics={metrics}")

    def log_hyperparams(self, params: Mapping[str, Any]) -> None:
        """Log hyperparameters and report training start.

        Args:
            params: Dictionary of hyperparameters to log
        """
        # Extract max_steps and num_epochs from params if not already set
        max_steps = self._max_steps or params.get("max_steps", 0)
        num_epochs = self._num_epochs or params.get("num_epochs", 1)

        # Update internal tracking if extracted from params
        if not self._max_steps and max_steps:
            self._max_steps = max_steps
        if not self._num_epochs and num_epochs:
            self._num_epochs = num_epochs

        self._callback.report_training_start(max_steps=max_steps, num_epochs=num_epochs)
        _logger.debug(f"log_hyperparams: max_steps={max_steps}, num_epochs={num_epochs}")

    def log_histogram(self, histogram: list[Any], step: int, name: str) -> None:
        """No-op: required by NeMo-RL's LoggerInterface.

        Jobs Service progress reporting has no histogram concept, so there is
        nothing to forward. Implemented only to satisfy the abstract base class.
        """
        return None

    def log_plot(self, figure: Any, step: int, name: str) -> None:
        """No-op: required by NeMo-RL's LoggerInterface.

        ``figure`` is a ``matplotlib.figure.Figure``; typed ``Any`` so we don't
        import matplotlib. Jobs Service has no figure/plot concept, so this is a
        no-op implemented only to satisfy the abstract base class.
        """
        return None

    def close(self) -> None:
        """Clean up resources."""
        if self._closed:
            return
        self._closed = True
        _logger.info("NemoRLLogger closing")
        self._callback.close()

    def __del__(self):
        """Cleanup when the logger is destroyed."""
        try:
            if hasattr(self, "_closed") and not self._closed:
                self.close()
        except Exception:
            # Silently ignore errors during interpreter shutdown
            pass
