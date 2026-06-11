# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment and ExperimentGroup entity definitions for the Intake service.

These are entity-store rows, distinct from ClickHouse telemetry. They hold the
durable, producer-supplied metadata that organizes telemetry into leaderboard
views. Rollups are derived from ClickHouse at read time.
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
    is_deleted: bool = Field(
        default=False,
        description=(
            "Soft-delete flag. DELETE flips this to true and cascades to child experiments. "
            "Deleted groups are hidden from list/get unless `filter[is_deleted]=true` is supplied."
        ),
    )


class Experiment(EntityBase):
    """A single agent/config run against a dataset: one row on a leaderboard.

    ``name`` is the producer-supplied, workspace-unique experiment id.
    """

    __entity_type__: ClassVar[str] = "experiment"

    experiment_group_id: str = Field(
        description=(
            "Entity id of the owning ExperimentGroup. Required — every Experiment must belong to a Group. "
            "Validated at create/update time; deleting a Group cascades to its Experiments."
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

    is_deleted: bool = Field(
        default=False,
        description=(
            "Soft-delete flag. DELETE flips this to true; on delete the entity is also renamed "
            "(`<name>-deleted-<utc-iso>`) so the original name is free for reuse. Deleted experiments "
            "are hidden from list/get and rejected by ATIF ingest unless `filter[is_deleted]=true`."
        ),
    )
