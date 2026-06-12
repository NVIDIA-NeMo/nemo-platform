# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request, response, and filter schemas for the Experiments API.

Response models are standalone: they translate from the stored entity via
``from_entity`` and carry rollup fields hydrated from ClickHouse at read time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nmp.common.entities.values import DatetimeFilter, Filter
from nmp.intake.entities.experiments import Experiment, ExperimentGroup
from nmp.intake.spans.domain import SpanStatus
from nmp.intake.spans.experiment_session_repository import ExperimentSessionRow
from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class ExperimentGroupRequest(BaseModel):
    """Request body for creating an ExperimentGroup."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Workspace-unique group name.")
    description: str | None = Field(default=None, description="Human-readable purpose of the group.")


class ExperimentRequest(BaseModel):
    """Request body for creating an Experiment."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Producer-supplied, workspace-unique experiment id.")
    experiment_group_id: str = Field(
        description="Entity id of the owning ExperimentGroup. Required — the group must already exist.",
    )
    dataset_name: str = Field(description="Producer-supplied dataset name.")
    dataset_version: str | None = Field(default=None, description="Producer-supplied dataset version.")
    source_link: AnyUrl | None = Field(default=None, description="Optional URL for the source experiment.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form producer metadata.")
    description: str | None = Field(default=None, description="Human-readable description.")
    summary: str | None = Field(default=None, description="Human-authored summary of results.")


class ExperimentGroupResponse(BaseModel):
    """ExperimentGroup as served by the API."""

    id: str
    name: str
    workspace: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    experiment_count: int = Field(
        default=0,
        description="Number of live (non-soft-deleted) experiments in this group.",
    )

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
    """Aggregate statistics over evaluator scores or session-level metric values."""

    sum: float | None = None
    mean: float | None = None
    median: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None
    count: int = 0


class ExperimentResponse(BaseModel):
    """Experiment as served by the API, including ClickHouse-hydrated rollups."""

    id: str
    name: str
    workspace: str
    experiment_group_id: str = Field(
        description="Entity id of the owning ExperimentGroup. Required for every Experiment.",
    )
    dataset_name: str
    dataset_version: str | None = None
    source_link: AnyUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    evaluator_names: list[str] = Field(default_factory=list)
    model_names: list[str] = Field(
        default_factory=list,
        description="Distinct model names observed across ingested sessions for this experiment.",
        json_schema_extra={"uniqueItems": True},
    )
    agent_names: list[str] = Field(
        default_factory=list,
        description="Distinct agent names observed across ingested sessions for this experiment.",
        json_schema_extra={"uniqueItems": True},
    )
    agent_versions: list[str] = Field(
        default_factory=list,
        description="Distinct agent versions observed across ingested sessions for this experiment.",
        json_schema_extra={"uniqueItems": True},
    )
    aggregate_scores: dict[str, EvaluatorAggregate] | None = None
    run_count: int = Field(
        default=0,
        description="Number of distinct ingested experiment sessions; one session is treated as one run.",
    )
    cost_usd: EvaluatorAggregate | None = None
    latency_ms: EvaluatorAggregate | None = None

    @classmethod
    def from_entity(cls, entity: Experiment) -> ExperimentResponse:
        return cls(
            id=entity.id,
            name=entity.name,
            workspace=entity.workspace,
            experiment_group_id=entity.experiment_group_id,
            dataset_name=entity.dataset_name,
            dataset_version=entity.dataset_version,
            source_link=entity.source_link,
            metadata=entity.metadata,
            description=entity.description,
            summary=entity.summary,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


class ExperimentGroupFilter(Filter):
    """Filter for listing ExperimentGroups."""

    name: str | None = Field(default=None, description="Filter groups by name.")
    is_deleted: bool | None = Field(
        default=None,
        description="When true, returns only soft-deleted groups. Omit (or false) to see only live groups.",
    )


class ExperimentFilter(Filter):
    """Filter for listing Experiments."""

    name: str | None = Field(default=None, description="Filter experiments by name.")
    experiment_group_id: str | None = Field(default=None, description="Filter experiments by owning group id.")
    dataset_name: str | None = Field(default=None, description="Filter experiments by dataset name.")
    dataset_version: str | None = Field(default=None, description="Filter experiments by dataset version.")
    created_by: str | None = Field(default=None, description="Filter experiments by the principal that created them.")
    created_at: DatetimeFilter | None = Field(
        default=None,
        description="Filter experiments by creation timestamp; supports `$gte` and `$lte` for ranges.",
    )
    updated_at: DatetimeFilter | None = Field(
        default=None,
        description="Filter experiments by last-updated timestamp; supports `$gte` and `$lte` for ranges.",
    )
    is_deleted: bool | None = Field(
        default=None,
        description=("When true, returns only soft-deleted experiments. Omit (or false) to see only live experiments."),
    )


class ExperimentSessionFilter(Filter):
    """Filter for listing ExperimentSessions."""

    test_case_id: str | None = Field(default=None, description="Filter by producer-supplied test case id.")
    status: str | None = Field(
        default=None, description="Filter by root-span status (success, error, cancelled, unknown)."
    )


class ExperimentSessionResponse(BaseModel):
    """One ingested session of an Experiment — a single test case execution.

    Hydrated from ClickHouse at read time by reading root/session membership from
    ``trace_index`` and joining page-bounded span/evaluator rollups.
    """

    workspace: str
    experiment_name: str
    session_id: str
    test_case_id: str | None = Field(
        default=None,
        description="Producer-supplied test case identifier; null when the producer did not set one.",
    )
    trace_id: str
    root_span_id: str

    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: float | None = None

    status: SpanStatus = Field(description="Root-span status: success, error, cancelled, or unknown.")
    input: str | None = Field(default=None, description="Root-span input text (the query).")

    input_tokens: int | None = Field(default=None, description="Sum of input tokens across this session's spans.")
    output_tokens: int | None = Field(default=None, description="Sum of output tokens across this session's spans.")
    cached_tokens: int | None = Field(default=None, description="Sum of cached tokens across this session's spans.")
    cost_total_usd: float | None = Field(default=None, description="Sum of cost across this session's spans.")

    evaluator_scores: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-evaluator session-mean score. Includes NUMERIC and BOOLEAN evaluator results only; "
            "text/categorical results are omitted."
        ),
    )

    @classmethod
    def from_row(cls, row: ExperimentSessionRow) -> ExperimentSessionResponse:
        return cls(
            workspace=row.workspace,
            experiment_name=row.experiment_name,
            session_id=row.session_id,
            test_case_id=row.test_case_id,
            trace_id=row.trace_id,
            root_span_id=row.root_span_id,
            started_at=row.started_at,
            ended_at=row.ended_at,
            latency_ms=row.latency_ms,
            status=row.status,
            input=row.input,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cached_tokens=row.cached_tokens,
            cost_total_usd=row.cost_total_usd,
            evaluator_scores=row.evaluator_scores,
        )
