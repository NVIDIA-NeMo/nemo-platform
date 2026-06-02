# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment and ExperimentGroup entity definitions for the Intake service.

These are entity-store (Postgres) entities, distinct from the ClickHouse-backed
telemetry (spans, evaluator_results). They hold the durable, producer-supplied
metadata that organizes telemetry into leaderboard-shaped views.

Cross-run rollups (per-evaluator aggregate scores, run count, and the unions of
evaluator/model names) are intentionally *not* stored here. They are derived from
ClickHouse and hydrated onto the read model at query time; see
``nmp.intake.api.v2.experiments.schemas.ExperimentResponse``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from nmp.common.entities.client import EntityBase
from pydantic import AnyUrl, Field


class ExperimentGroup(EntityBase):
    """A named container of Experiments pursuing a single optimization goal.

    A group does not constrain dataset or agent identity across its Experiments.
    """

    __entity_type__: ClassVar[str] = "experiment_group"

    description: str | None = Field(default=None, description="Human-readable purpose of the group.")


class Experiment(EntityBase):
    """A single agent/config run against a dataset: one row on a leaderboard.

    ``name`` is the producer-supplied, workspace-unique experiment id (e.g.
    ``"terminal-bench-2_claude-code_opus_baseline"``); create is keyed on it.
    """

    __entity_type__: ClassVar[str] = "experiment"

    experiment_group_id: str | None = Field(
        default=None,
        description=(
            "Entity id of the owning ExperimentGroup; null when ungrouped. A soft reference: "
            "it is not validated on write, and deleting a group does not cascade to its Experiments."
        ),
    )

    agent_name: str = Field(description="Name of the agent under test.")
    agent_version: str = Field(description="Version of the agent under test.")

    dataset_name: str = Field(description="Producer-supplied dataset name.")
    dataset_version: str | None = Field(default=None, description="Producer-supplied dataset version.")
    source_link: AnyUrl | None = Field(default=None, description="Optional URL for the source experiment.")

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form producer metadata (config snapshot, domain-specific attributes, etc.).",
    )

    description: str | None = Field(default=None, description="Human-readable description of the experiment.")
    summary: str | None = Field(default=None, description="Human-authored summary of results.")
