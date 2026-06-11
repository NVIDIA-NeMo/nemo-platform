# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bridge HuggingFace Trainer callbacks to Jobs-service progress reporting."""

import math
from typing import Any

from nmp.unsloth.tasks.training.backends.callbacks import TrainingProgressCallback


def _epoch_from_value(raw_epoch: float | int, num_epochs: int) -> int:
    """Map HF fractional epoch values to a 1-based epoch index."""
    return max(1, min(num_epochs, math.ceil(float(raw_epoch))))


def create_hf_trainer_progress_callback(
    progress_callback: TrainingProgressCallback,
    *,
    backend: str = "unsloth",
) -> Any:
    """Build a HuggingFace :class:`~transformers.TrainerCallback` for Jobs reporting.

    Import is deferred so this module stays importable without ``transformers``.
    """
    from transformers import TrainerCallback

    class HfTrainerProgressCallback(TrainerCallback):
        def __init__(self) -> None:
            self._progress = progress_callback
            self._backend = backend
            self._num_epochs = 1

        def on_train_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            self._num_epochs = max(1, int(args.num_train_epochs))
            max_steps = max(1, int(state.max_steps))
            self._progress.report_training_start(
                max_steps=max_steps,
                num_epochs=self._num_epochs,
                backend=self._backend,
            )

        def on_log(
            self, args: Any, state: Any, control: Any, logs: dict[str, Any] | None = None, **kwargs: Any
        ) -> None:
            if not logs or "loss" not in logs:
                return

            epoch_raw = logs.get("epoch", state.epoch if state.epoch is not None else 0)
            self._progress.report_train_step(
                step=int(state.global_step),
                epoch=_epoch_from_value(epoch_raw, self._num_epochs),
                loss=float(logs["loss"]),
                lr=float(logs["learning_rate"]) if logs.get("learning_rate") is not None else None,
                grad_norm=float(logs["grad_norm"]) if logs.get("grad_norm") is not None else None,
                backend=self._backend,
            )

        def on_evaluate(
            self,
            args: Any,
            state: Any,
            control: Any,
            metrics: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> None:
            if not metrics or "eval_loss" not in metrics:
                return

            epoch_raw = metrics.get("epoch", state.epoch if state.epoch is not None else 0)
            self._progress.report_validation(
                step=int(state.global_step),
                epoch=_epoch_from_value(epoch_raw, self._num_epochs),
                val_loss=float(metrics["eval_loss"]),
                backend=self._backend,
            )

        def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
            checkpoint_path = kwargs.get("checkpoint_folder", args.output_dir)
            epoch_raw = state.epoch if state.epoch is not None else 0
            self._progress.report_checkpoint_saved(
                step=int(state.global_step),
                epoch=_epoch_from_value(epoch_raw, self._num_epochs),
                checkpoint_path=str(checkpoint_path) if checkpoint_path is not None else None,
                backend=self._backend,
            )

    return HfTrainerProgressCallback()
