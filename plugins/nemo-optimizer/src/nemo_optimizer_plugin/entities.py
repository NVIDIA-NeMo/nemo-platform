# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optimizer plugin entity definitions — stored in the NeMo Platform entity store."""

from __future__ import annotations

from enum import StrEnum

from nemo_platform_plugin.entity import NemoEntity
from pydantic import Field


class InsightStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DELETED = "deleted"


class Insight(NemoEntity, entity_type="insight"):
    """A named, persistent problem in the AUT.

    Status transitions allowed: ``open → in_progress``, ``open → resolved``,
    ``open → deleted``, ``in_progress → resolved``, ``in_progress → deleted``,
    ``resolved → in_progress`` (reopening). Same-state writes are idempotent.
    All other transitions return 400.
    """

    agent: str = Field(description="Name of the AgentRegistration this insight is about.")
    description: str = Field(description="The problem statement: specific enough to act on.")
    status: InsightStatus = Field(default=InsightStatus.OPEN)
    eval_dataset_row_refs: list[str] = Field(
        default_factory=list,
        description="Evaluator dataset row ids attached as regression tests.",
    )
