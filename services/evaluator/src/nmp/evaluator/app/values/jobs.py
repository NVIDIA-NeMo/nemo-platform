# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job-related value types."""

from __future__ import annotations

from nemo_evaluator_sdk.enums import TaskStatus
from pydantic import BaseModel, Field


class EvaluationStatusDetails(BaseModel):
    """Details about the status of the evaluation."""

    message: str | None = Field(
        default=None,
        description="A message about the status of the evaluation.",
    )
    task_status: dict[str, TaskStatus] = Field(
        default_factory=dict,
        description="Information about the status of every task.",
    )
    progress: float | None = Field(
        default=None,
        description="The progress of the evaluation, between 0.0 and 100.0.",
    )
    samples_processed: int | None = Field(
        default=None, description="The number of samples from the dataset that have been processed for evaluation."
    )
