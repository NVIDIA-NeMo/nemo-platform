# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment and ExperimentGroup entity definitions for the Intake service.

These are entity-store rows, distinct from ClickHouse telemetry. They hold the
durable, producer-supplied metadata that organizes telemetry into leaderboard
views. Rollups are derived from ClickHouse at read time.

NOTE: The public API and Studio already call this concept an "Evaluation" — but
the entity here is intentionally still ``Experiment`` (``__entity_type__ =
"experiment"``, ``parent_experiment_id``). Renaming the entity, its
``__entity_type__``, and its stored fields is a breaking storage change that
requires a one-time data migration of existing rows, so it is deferred to a
later pass. Until then the API layer maps Evaluation ⇄ this Experiment entity.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, ClassVar

from nmp.common.entities.client import EntityBase
from pydantic import AnyUrl, Field, field_validator


def _stringify_metadata(value: Any) -> Any:
    """Schema-on-read coercion for ``metadata``, which tightened from ``dict[str, Any]`` to
    ``dict[str, str]``. Legacy rows may hold non-string values; stringify them (JSON-encoding
    structured values) so old rows still read. Non-dict values pass through for pydantic to handle."""
    if not isinstance(value, dict):
        return value
    return {key: val if isinstance(val, str) else json.dumps(val) for key, val in value.items()}


class ExperimentGroup(EntityBase):
    """A named container of Experiments pursuing a single optimization goal.

    A group does not constrain dataset or agent identity across its Experiments.
    """

    __entity_type__: ClassVar[str] = "experiment_group"

    description: str | None = Field(default=None, description="Human-readable purpose of the group.")
    insight_id: str | None = Field(
        default=None,
        description="Reference to an external insight that seeded this group, if any.",
    )
    summary: str | None = Field(default=None, description="Human- or agent-authored summary of the group's findings.")
    metadata: dict[str, str] | None = Field(default=None, description="Free-form producer metadata for the group.")

    @field_validator("metadata", mode="before")
    @classmethod
    def _coerce_metadata(cls, value: Any) -> Any:
        return _stringify_metadata(value)

    default_sort: str = Field(
        default="-created_at",
        description=(
            "Default sort for this group's experiments list, as a `sort`-param string (leading '-' = "
            "descending); defaults to '-created_at'. Accepts any field the experiments list `sort` "
            "param does. The client applies it as the list `sort` param; this endpoint does not "
            "consult it."
        ),
    )

    @field_validator("default_sort", mode="before")
    @classmethod
    def _default_sort_fallback(cls, value: Any) -> Any:
        """Upgrade legacy rows to the default. Groups persisted before this field was a non-null string
        stored ``default_sort`` as ``null`` (or, earlier, a ``SortCriterion`` list); the entity store is
        schema-on-read, so coerce anything that isn't a usable string to the default on read."""
        return value if isinstance(value, str) else "-created_at"

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

    Exposed as "Evaluation" by the API/Studio; still stored as ``experiment``
    here pending the entity rename + data migration (see module docstring).
    """

    __entity_type__: ClassVar[str] = "experiment"

    experiment_group_id: str = Field(
        description=(
            "Entity id of the owning ExperimentGroup. Required — every Experiment must belong to a Group. "
            "Validated at create/update time; deleting a Group cascades to its Experiments."
        ),
    )

    dataset_name: str = Field(description="Producer-supplied dataset name.")
    dataset_version: str | None = Field(default=None, description="Producer-supplied dataset version.")
    source_link: AnyUrl | None = Field(default=None, description="Optional URL for the source experiment.")

    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Free-form producer metadata (config snapshot, domain-specific attributes, etc.).",
    )

    @field_validator("metadata", mode="before")
    @classmethod
    def _coerce_metadata(cls, value: Any) -> Any:
        return _stringify_metadata(value)

    description: str | None = Field(default=None, description="Human-readable description of the experiment.")

    parent_experiment_id: str | None = Field(
        default=None,
        description="Entity id of the experiment this one was derived from (e.g. a variant of a baseline), if any.",
    )
    status: str | None = Field(
        default=None,
        description="Producer-defined lifecycle status of the experiment.",
    )
    root_cause: str | None = Field(
        default=None,
        description="Human- or agent-authored explanation of the experiment's outcome (e.g. why it was killed).",
    )

    is_deleted: bool = Field(
        default=False,
        description=(
            "Soft-delete flag. DELETE flips this to true; on delete the entity is also renamed "
            "(`<name>-deleted-<utc-iso>`) so the original name is free for reuse. Deleted experiments "
            "are hidden from list/get and rejected by ATIF ingest unless `filter[is_deleted]=true`."
        ),
    )

    pinned_at: datetime | None = Field(
        default=None,
        description=(
            "Timestamp at which the experiment was pinned to the top of the list, or null if unpinned. "
            "Managed via POST/DELETE /experiments/{name}/pin (not via the create or update body). "
            "Pin state is workspace-shared: every user with workspace access sees the same pinned set."
        ),
    )
