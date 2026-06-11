# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for HuggingFace Trainer → Jobs progress bridge."""

from unittest.mock import MagicMock

import pytest
from nmp.unsloth.tasks.training.backends.callbacks import TrainingProgressCallback
from nmp.unsloth.tasks.training.backends.hf_trainer_callback import (
    _epoch_from_value,
    create_hf_trainer_progress_callback,
)


class TestEpochFromValue:
    def test_fractional_epoch_maps_to_one(self):
        assert _epoch_from_value(0.01314, 1) == 1

    def test_completed_epoch_capped_at_num_epochs(self):
        assert _epoch_from_value(1.0, 1) == 1
        assert _epoch_from_value(2.0, 2) == 2


class TestHfTrainerProgressCallback:
    @pytest.fixture
    def progress(self) -> tuple[TrainingProgressCallback, MagicMock]:
        reporter = MagicMock()
        reporter.fetch_current_metrics.return_value = {"train_loss": [], "val_loss": []}
        return TrainingProgressCallback(reporter), reporter

    def test_on_log_reports_train_step(self, progress: tuple[TrainingProgressCallback, MagicMock]) -> None:
        callback, reporter = progress
        hf_callback = create_hf_trainer_progress_callback(callback)

        args = MagicMock(num_train_epochs=1)
        state = MagicMock(max_steps=77, global_step=8, epoch=0.1)

        hf_callback.on_train_begin(args, state, MagicMock())
        hf_callback.on_log(
            args, state, MagicMock(), logs={"loss": 2.89, "learning_rate": 5e-5, "grad_norm": 10.6, "epoch": 0.1}
        )

        reporter.report_running.assert_called()
        kwargs = reporter.report_running.call_args.kwargs
        assert kwargs["phase"] == "training"
        assert kwargs["step"] == 8
        assert kwargs["train_loss"] == 2.89
        assert kwargs["lr"] == 5e-5
        assert kwargs["grad_norm"] == 10.6
        assert kwargs["backend"] == "unsloth"
        assert kwargs["metrics"]["train_loss"][-1]["value"] == 2.89

    def test_on_log_skips_non_train_logs(self, progress: tuple[TrainingProgressCallback, MagicMock]) -> None:
        callback, reporter = progress
        hf_callback = create_hf_trainer_progress_callback(callback)

        args = MagicMock(num_train_epochs=1)
        state = MagicMock(max_steps=77, global_step=8, epoch=0.1)
        hf_callback.on_train_begin(args, state, MagicMock())

        reporter.report_running.reset_mock()
        hf_callback.on_log(args, state, MagicMock(), logs={"eval_loss": 1.2})

        reporter.report_running.assert_not_called()

    def test_on_evaluate_reports_validation(self, progress: tuple[TrainingProgressCallback, MagicMock]) -> None:
        callback, reporter = progress
        hf_callback = create_hf_trainer_progress_callback(callback)

        args = MagicMock(num_train_epochs=1)
        state = MagicMock(max_steps=77, global_step=40, epoch=0.5)
        hf_callback.on_train_begin(args, state, MagicMock())

        reporter.report_running.reset_mock()
        hf_callback.on_evaluate(args, state, MagicMock(), metrics={"eval_loss": 1.75, "epoch": 0.5})

        kwargs = reporter.report_running.call_args.kwargs
        assert kwargs["phase"] == "validation"
        assert kwargs["val_loss"] == 1.75
        assert kwargs["metrics"]["val_loss"][-1]["value"] == 1.75
