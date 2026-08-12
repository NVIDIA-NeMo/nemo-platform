# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Wiring tests for the RL TrainingProgressCallback subclass.

The behaviour lives in the shared base
(``packages/nmp_customization_common/tests/training/test_callbacks.py``); what is
RL-specific is only which base it inherits and that it stays unstamped.
"""

from __future__ import annotations

from nmp.customization_common.training.callbacks import (
    TrainingProgressCallback as SharedTrainingProgressCallback,
)
from nmp.rl.tasks.training.backends.nemo_rl.callbacks import TrainingProgressCallback


def test_rl_callback_subclasses_the_shared_one() -> None:
    """RL used to carry a standalone copy; accumulation fixes must land once."""
    assert issubclass(TrainingProgressCallback, SharedTrainingProgressCallback)


def test_rl_callback_adds_no_backend_field() -> None:
    """Stamping `backend` would change RL's status-detail shape on the wire.

    unsloth opts in; automodel and RL deliberately do not.
    """
    assert TrainingProgressCallback._default_backend is None
