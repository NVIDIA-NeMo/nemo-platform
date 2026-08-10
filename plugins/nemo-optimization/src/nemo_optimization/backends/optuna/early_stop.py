# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Early stop when ``optimizer.target`` is met (single-objective only)."""

from __future__ import annotations

import optuna
from optuna.study import StudyDirection


def maybe_stop_if_target_met(
    study: optuna.Study,
    scores: list[float],
    *,
    target: float | None,
    directions: list[StudyDirection],
) -> None:
    """Stop the study when the sole objective reaches ``optimizer.target``."""
    if target is None or len(scores) != 1 or len(directions) != 1:
        return

    score = scores[0]
    if directions[0] == StudyDirection.MAXIMIZE and score >= target:
        study.stop()
    elif directions[0] == StudyDirection.MINIMIZE and score <= target:
        study.stop()
