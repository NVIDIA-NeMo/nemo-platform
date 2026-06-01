# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request, response, and filter schemas for the Experiments API.

Response models are standalone (not entity subclasses): they translate from the
stored entity via ``from_entity`` and carry rollup fields that are hydrated from
ClickHouse at read time. In this PR the rollups are always defaults; the
hydration path lands in a later PR.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nmp.common.entities.values import Filter
from nmp.intake.entities.experiments import Experiment, ExperimentGroup
from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Requests (workspace comes from the route parameter)
# =============================================================================


class ExperimentGroupRequest(BaseModel):
    """Request body for creating an ExperimentGroup."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Workspace-unique group name.")
    description: str | None = Field(default=None, description="Human-readable purpose of the group.")


class ExperimentRequest(BaseModel):
    """Request body for creating an Experiment."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Producer-supplied, workspace-unique experiment id.")
    experiment_group_id: str | None = Field(
        default=None,
        description="Entity id of the owning ExperimentGroup; optional. Soft reference, not validated.",
    )
    agent_name: str = Field(description="Name of the agent under test.")
    agent_version: str = Field(description="Version of the agent under test.")
    dataset_id: str = Field(description="Producer-supplied dataset identifier.")
    dataset_version: str | None = Field(default=None, description="Producer-supplied dataset version.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form producer metadata.")
    description: str | None = Field(default=None, description="Human-readable description.")
    summary: str | None = Field(default=None, description="Human-authored summary of results.")


# =============================================================================
# Responses
# =============================================================================


class ExperimentGroupResponse(BaseModel):
    """ExperimentGroup as served by the API."""

    id: str
    name: str
    workspace: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_entity(cls, entity: ExperimentGroup) -> ExperimentGroupResponse:
        return cls(
            id=entity.id,
            name=entity.name,
            workspace=entity.workspace,
            description=entity.description,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


class EvaluatorAggregate(BaseModel):
    """Cross-run statistics for one evaluator. Populated by the rollup path (later PR)."""

    mean: float | None = None
    median: float | None = None
    stddev: float | None = None
    n_runs: int = 0


class ExperimentResponse(BaseModel):
    """Experiment as served by the API, including ClickHouse-hydrated rollups."""

    id: str
    name: str
    workspace: str
    experiment_group_id: str | None = Field(
        default=None,
        description="Entity id of the owning ExperimentGroup; null when ungrouped. Soft reference, not validated.",
    )
    agent_name: str
    agent_version: str
    dataset_id: str
    dataset_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Hydrated from ClickHouse at read time in a later PR; defaults until then.
    evaluator_names: list[str] = Field(default_factory=list)
    aggregate_scores: dict[str, EvaluatorAggregate] | None = None
    run_count: int = 0

    @classmethod
    def from_entity(cls, entity: Experiment) -> ExperimentResponse:
        return cls(
            id=entity.id,
            name=entity.name,
            workspace=entity.workspace,
            experiment_group_id=entity.experiment_group_id,
            agent_name=entity.agent_name,
            agent_version=entity.agent_version,
            dataset_id=entity.dataset_id,
            dataset_version=entity.dataset_version,
            metadata=entity.metadata,
            description=entity.description,
            summary=entity.summary,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


# =============================================================================
# List filters (declarative; the entity store applies them)
# =============================================================================


class ExperimentGroupFilter(Filter):
    """Filter for listing ExperimentGroups."""

    name: str | None = Field(default=None, description="Filter groups by name.")


class ExperimentFilter(Filter):
    """Filter for listing Experiments."""

    name: str | None = Field(default=None, description="Filter experiments by name.")
    experiment_group_id: str | None = Field(default=None, description="Filter experiments by owning group id.")
    agent_name: str | None = Field(default=None, description="Filter experiments by agent name.")
    dataset_id: str | None = Field(default=None, description="Filter experiments by dataset id.")
