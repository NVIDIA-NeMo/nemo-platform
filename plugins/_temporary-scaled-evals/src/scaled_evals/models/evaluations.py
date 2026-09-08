# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

RewardValue = bool | int | float | str


class EvaluationResultSummary(BaseModel):
    """Framework-agnostic reduction persisted to queryable evaluation columns."""

    model_config = ConfigDict(frozen=True)

    reward: RewardValue | None = None
    n_trials: int | None = None
    n_completed: int | None = None
    n_errored: int | None = None
    n_failed_solve: int | None = None
    exception_counts: dict[str, int] = Field(default_factory=dict)
    finished_at: str | None = None

    def legacy_numeric_reward(self) -> float | None:
        """Numeric projection retained for existing Harbor/Gym query paths."""
        if isinstance(self.reward, bool) or not isinstance(self.reward, int | float):
            return None
        return float(self.reward)


class EvaluationResultWrite(BaseModel):
    """A trustworthy terminal result payload ready to persist on an evaluation row."""

    model_config = ConfigDict(frozen=True)

    result: dict[str, Any] = Field(default_factory=dict)
    summary: EvaluationResultSummary = Field(default_factory=EvaluationResultSummary)
    extra_detail: str | None = None

    def status_detail(self) -> str | None:
        detail = (
            f"{self.summary.n_completed}/{self.summary.n_trials} trials completed"
            if self.summary.n_trials is not None
            else None
        )
        if self.extra_detail:
            return f"{detail}; {self.extra_detail}" if detail else self.extra_detail
        return detail
