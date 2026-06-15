# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Training progress callback shared by the customization backends.

Composes a :class:`nmp.customization_common.training.progress.JobsServiceProgressReporter`
and provides training-specific methods. Metric accumulation: ``train_loss`` and
``val_loss`` are accumulated as time-series lists and included in every
``status_details`` update under a ``metrics`` key, enabling loss-curve
reconstruction from job status.

Backends subclass this and set :attr:`_default_backend`: unsloth stamps a
``backend`` field on each report (``"unsloth"``); automodel leaves it ``None`` so
no ``backend`` key is added (preserving its status-detail shape). Callers may also
pass ``backend`` per call (e.g. unsloth's HF trainer callback).
"""

import logging
from typing import ClassVar

from nmp.customization_common.training.progress import JobsServiceProgressReporter

logger = logging.getLogger(__name__)


class TrainingProgressCallback:
    """Report training progress to the Jobs service."""

    #: Backend name stamped on each report when a per-call ``backend`` isn't given.
    #: ``None`` means no ``backend`` field is added.
    _default_backend: ClassVar[str | None] = None

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

    def _resolve_backend(self, backend: str | None) -> str | None:
        return backend if backend is not None else self._default_backend

    def _build_metrics_summary(self) -> dict[str, list[dict[str, float | int]]]:
        """Build the accumulated metrics payload for inclusion in status_details."""
        return {
            "train_loss": list(self._train_metrics),
            "val_loss": list(self._val_metrics),
        }

    def report_training_start(self, max_steps: int, num_epochs: int, *, backend: str | None = None) -> None:
        """Report that training has started with schedule information."""
        self._reporter.configure_progress_tracking(max_steps, num_epochs)
        details: dict[str, object] = {"step": 0, "max_steps": max_steps, "num_epochs": num_epochs}
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="training", **details)

    def report_train_step(
        self,
        step: int,
        epoch: int,
        loss: float,
        lr: float | None = None,
        grad_norm: float | None = None,
        *,
        backend: str | None = None,
    ) -> None:
        """Report training step with metrics."""
        self._train_metrics.append({"step": step, "epoch": epoch, "value": loss})
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
            "train_loss": loss,
            "lr": lr,
            "grad_norm": grad_norm,
            "metrics": self._build_metrics_summary(),
        }
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="training", **details)

    def report_validation(self, step: int, epoch: int, val_loss: float, *, backend: str | None = None) -> None:
        """Report validation results."""
        self._val_metrics.append({"step": step, "epoch": epoch, "value": val_loss})
        details: dict[str, object] = {
            "step": step,
            "epoch": epoch,
            "val_loss": val_loss,
            "metrics": self._build_metrics_summary(),
        }
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="validation", **details)

    def report_checkpoint_saved(
        self,
        step: int,
        epoch: int,
        checkpoint_path: str | None = None,
        *,
        backend: str | None = None,
    ) -> None:
        """Report that a checkpoint was saved."""
        details: dict[str, object] = {"step": step, "epoch": epoch, "checkpoint_path": checkpoint_path}
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="checkpoint_saved", **details)

    def report_epoch_end(self, step: int, epoch: int, *, backend: str | None = None) -> None:
        """Report that an epoch has completed."""
        details: dict[str, object] = {"step": step, "epoch": epoch}
        resolved = self._resolve_backend(backend)
        if resolved is not None:
            details["backend"] = resolved
        self._reporter.report_running(phase="epoch_end", **details)

    def close(self) -> None:
        """Clean up resources."""
        self._reporter.close()
