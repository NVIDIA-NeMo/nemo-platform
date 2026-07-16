# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request, response, and filter schemas for the Evaluations API.

Response models are standalone: they translate from the stored entity via
``from_entity`` and carry rollup fields hydrated from ClickHouse at read time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self

from nmp.common.entities.values import DatetimeFilter, Filter, NumberFilter, map_entity_field
from nmp.intake.entities.experiments import Experiment, ExperimentGroup
from nmp.intake.spans.domain import (
    INTAKE_PREVIEW_PAYLOAD_CHAR_LIMIT,
    IntakeResponseMode,
    SpanStatus,
)
from nmp.intake.spans.evaluation_session_repository import EvaluationSessionRow
from nmp.intake.spans.storage import text_for_mode
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, computed_field, model_validator

EvaluationSessionMode = IntakeResponseMode


class ExperimentGroupRequest(BaseModel):
    """Request body for creating an ExperimentGroup."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Workspace-unique group name.")
    description: str | None = Field(default=None, description="Human-readable purpose of the group.")
    insight_id: str | None = Field(
        default=None, description="Reference to an external insight that seeded this group, if any."
    )
    summary: str | None = Field(default=None, description="Human- or agent-authored summary of the group's findings.")
    metadata: dict[str, str] | None = Field(default=None, description="Free-form producer metadata for the group.")
    default_sort: str = Field(
        default="-created_at",
        description=(
            "Default sort for this group's evaluations list, as a `sort`-param string: a comma-separated, "
            "ordered list of fields where the first is the primary sort and the rest break ties (leading "
            "'-' on a field = descending), e.g. '-evaluators.reward.mean,cost_usd.mean'. Defaults to "
            "'-created_at'. Accepts any field the evaluations list `sort` param does; clients apply it as "
            "the list `sort` param."
        ),
    )


class EvaluationRequest(BaseModel):
    """Request body for creating an Evaluation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Producer-supplied, workspace-unique evaluation id.")
    experiment_group_id: str = Field(
        description="Entity id of the owning ExperimentGroup. Required — the group must already exist.",
    )
    dataset_name: str = Field(description="Producer-supplied dataset name.")
    dataset_version: str | None = Field(default=None, description="Producer-supplied dataset version.")
    source_link: AnyUrl | None = Field(default=None, description="Optional URL for the source evaluation.")
    metadata: dict[str, str] = Field(default_factory=dict, description="Free-form producer metadata.")
    description: str | None = Field(default=None, description="Human-readable description.")
    parent_evaluation_id: str | None = Field(
        default=None,
        description="Entity id of the evaluation this one was derived from (e.g. a variant of a baseline), if any.",
    )
    parent_experiment_id: str | None = Field(
        default=None,
        deprecated=True,
        description="Deprecated alias for parent_evaluation_id.",
    )
    status: str | None = Field(default=None, description="Producer-defined lifecycle status of the evaluation.")
    root_cause: str | None = Field(
        default=None,
        description="Human- or agent-authored explanation of the evaluation's outcome (e.g. why it was killed).",
    )

    @model_validator(mode="after")
    def _coalesce_deprecated_parent(self) -> Self:
        """Accept the deprecated ``parent_experiment_id`` alias; the canonical field wins if both are set.

        Read the raw value via ``__dict__`` to avoid tripping the field's deprecation warning on
        every request.
        """
        deprecated_parent = self.__dict__.get("parent_experiment_id")
        if self.parent_evaluation_id is None and deprecated_parent is not None:
            self.parent_evaluation_id = deprecated_parent
        return self


class ExperimentGroupResponse(BaseModel):
    """ExperimentGroup as served by the API."""

    id: str
    name: str
    workspace: str
    description: str | None = None
    insight_id: str | None = None
    summary: str | None = None
    metadata: dict[str, str] | None = None
    default_sort: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    evaluation_count: int = Field(
        default=0,
        description="Number of live (non-soft-deleted) evaluations in this group.",
    )

    @computed_field(deprecated=True, description="Deprecated alias for evaluation_count.")  # type: ignore[prop-decorator]
    @property
    def experiment_count(self) -> int:
        return self.evaluation_count

    @classmethod
    def from_entity(cls, entity: ExperimentGroup) -> ExperimentGroupResponse:
        return cls(
            id=entity.id,
            name=entity.name,
            workspace=entity.workspace,
            description=entity.description,
            insight_id=entity.insight_id,
            summary=entity.summary,
            metadata=entity.metadata,
            default_sort=entity.default_sort,
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


class EvaluationResponse(BaseModel):
    """Evaluation as served by the API, including ClickHouse-hydrated rollups."""

    id: str
    name: str
    workspace: str
    experiment_group_id: str = Field(
        description="Entity id of the owning ExperimentGroup. Required for every Evaluation.",
    )
    dataset_name: str
    dataset_version: str | None = None
    source_link: AnyUrl | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    parent_evaluation_id: str | None = None
    status: str | None = None
    root_cause: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pinned_at: datetime | None = Field(
        default=None,
        description=(
            "Timestamp at which the evaluation was pinned, or null if unpinned. "
            "Managed via POST/DELETE /evaluations/{name}/pin."
        ),
        json_schema_extra={"nullable": True},
    )

    evaluator_names: list[str] = Field(default_factory=list)
    model_names: list[str] = Field(
        default_factory=list,
        description="Distinct model names observed across ingested sessions for this evaluation.",
        json_schema_extra={"uniqueItems": True},
    )
    agent_names: list[str] = Field(
        default_factory=list,
        description="Distinct agent names observed across ingested sessions for this evaluation.",
        json_schema_extra={"uniqueItems": True},
    )
    agent_versions: list[str] = Field(
        default_factory=list,
        description="Distinct agent versions observed across ingested sessions for this evaluation.",
        json_schema_extra={"uniqueItems": True},
    )
    aggregate_scores: dict[str, EvaluatorAggregate] | None = None
    run_count: int = Field(
        default=0,
        description="Number of distinct ingested evaluation sessions; one session is treated as one run.",
    )
    cost_usd: EvaluatorAggregate | None = None
    latency_ms: EvaluatorAggregate | None = None

    @computed_field(deprecated=True, description="Deprecated alias for parent_evaluation_id.")  # type: ignore[prop-decorator]
    @property
    def parent_experiment_id(self) -> str | None:
        return self.parent_evaluation_id

    @classmethod
    def from_entity(cls, entity: Experiment) -> EvaluationResponse:
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
            parent_evaluation_id=entity.parent_experiment_id,
            status=entity.status,
            root_cause=entity.root_cause,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            pinned_at=entity.pinned_at,
        )


class MetricStatFilters(BaseModel):
    """Numeric range filters keyed by rollup aggregate stat.

    Declaring each stat explicitly (rather than an open ``dict[str, NumberFilter]``) makes the valid
    stats visible in the OpenAPI schema, e.g. ``filter[cost_usd.mean][$lte]=0.5``. These stats must
    stay in sync with the runtime sort/filter grammar (``_METRIC_STATS`` in the evaluations
    endpoints); a unit test guards the parity.
    """

    model_config = ConfigDict(extra="forbid")

    sum: NumberFilter | None = None
    mean: NumberFilter | None = None
    median: NumberFilter | None = None
    p90: NumberFilter | None = None
    p95: NumberFilter | None = None
    p99: NumberFilter | None = None
    count: NumberFilter | None = None


class ExperimentGroupFilter(Filter):
    """Filter for listing ExperimentGroups."""

    name: str | None = Field(default=None, description="Filter groups by name.")
    is_deleted: bool | None = Field(
        default=None,
        description="When true, returns only soft-deleted groups. Omit (or false) to see only live groups.",
    )
    metadata: Annotated[dict[str, str] | None, map_entity_field("data.metadata", namespace=True)] = Field(
        default=None,
        description="Filter by a metadata key/value pair, e.g. filter[metadata.model]=claude-opus-4-8.",
    )


class EvaluationFilter(Filter):
    """Filter for listing Evaluations."""

    name: str | None = Field(default=None, description="Filter evaluations by name.")
    experiment_group_id: str | None = Field(default=None, description="Filter evaluations by owning group id.")
    dataset_name: str | None = Field(default=None, description="Filter evaluations by dataset name.")
    dataset_version: str | None = Field(default=None, description="Filter evaluations by dataset version.")
    created_by: str | None = Field(default=None, description="Filter evaluations by the principal that created them.")
    created_at: DatetimeFilter | None = Field(
        default=None,
        description="Filter evaluations by creation timestamp; supports `$gte` and `$lte` for ranges.",
    )
    updated_at: DatetimeFilter | None = Field(
        default=None,
        description="Filter evaluations by last-updated timestamp; supports `$gte` and `$lte` for ranges.",
    )
    is_deleted: bool | None = Field(
        default=None,
        description=("When true, returns only soft-deleted evaluations. Omit (or false) to see only live evaluations."),
    )
    is_pinned: bool | None = Field(
        default=None,
        description=(
            "When true, returns only pinned evaluations. When false, returns only unpinned evaluations. "
            "Omit to return both."
        ),
    )
    metadata: Annotated[dict[str, str] | None, map_entity_field("data.metadata", namespace=True)] = Field(
        default=None,
        description="Filter by a metadata key/value pair, e.g. filter[metadata.model]=claude-opus-4-8.",
    )
    # Rollup-metric filters. These live in ClickHouse, not the entity store, so they're declared as
    # self-mapping namespaces (the path is left untranslated) and applied in the application layer
    # after rollup hydration rather than forwarded to Postgres. Stat sub-paths mirror the sort grammar:
    # filter[cost_usd.mean][gte]=0.8, filter[evaluators.<name>.mean][lte]=0.5, filter[run_count][gte]=5.
    run_count: Annotated[NumberFilter | None, map_entity_field("run_count")] = Field(
        default=None, description="Filter by run count, e.g. filter[run_count][$gte]=5."
    )
    cost_usd: Annotated[MetricStatFilters | None, map_entity_field("cost_usd", namespace=True)] = Field(
        default=None, description="Filter by a cost_usd rollup stat, e.g. filter[cost_usd.mean][$lte]=0.5."
    )
    latency_ms: Annotated[MetricStatFilters | None, map_entity_field("latency_ms", namespace=True)] = Field(
        default=None, description="Filter by a latency_ms rollup stat, e.g. filter[latency_ms.p95][$lte]=1000."
    )
    evaluators: Annotated[dict[str, MetricStatFilters] | None, map_entity_field("evaluators", namespace=True)] = Field(
        default=None,
        description="Filter by an evaluator rollup stat, e.g. filter[evaluators.<name>.mean][$gte]=0.8.",
    )


class EvaluationSessionFilter(Filter):
    """Filter for listing EvaluationSessions."""

    test_case_id: str | None = Field(default=None, description="Filter by producer-supplied test case id.")
    status: str | None = Field(
        default=None, description="Filter by root-span status (success, error, cancelled, unknown)."
    )


class EvaluationSessionResponse(BaseModel):
    """One ingested session of an Evaluation — a single test case execution.

    Hydrated from ClickHouse at read time by reading root/session membership from
    ``trace_index`` and joining page-bounded span/evaluator rollups.
    """

    workspace: str
    evaluation_name: str

    @computed_field(deprecated=True, description="Deprecated alias for evaluation_name.")  # type: ignore[prop-decorator]
    @property
    def experiment_name(self) -> str:
        return self.evaluation_name

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
    input: str | None = Field(
        default=None,
        description=(
            f"Root-span input text. Omitted in summary mode and truncated to {INTAKE_PREVIEW_PAYLOAD_CHAR_LIMIT} "
            "characters in preview mode."
        ),
    )
    output: str | None = Field(
        default=None,
        description=(
            f"Root-span output text. Omitted in summary mode and truncated to {INTAKE_PREVIEW_PAYLOAD_CHAR_LIMIT} "
            "characters in preview mode."
        ),
    )

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
    def from_row(
        cls,
        row: EvaluationSessionRow,
        *,
        mode: EvaluationSessionMode = "detailed",
    ) -> EvaluationSessionResponse:
        return cls(
            workspace=row.workspace,
            evaluation_name=row.evaluation_name,
            session_id=row.session_id,
            test_case_id=row.test_case_id,
            trace_id=row.trace_id,
            root_span_id=row.root_span_id,
            started_at=row.started_at,
            ended_at=row.ended_at,
            latency_ms=row.latency_ms,
            status=row.status,
            input=text_for_mode(row.input, mode=mode),
            output=text_for_mode(row.output, mode=mode),
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cached_tokens=row.cached_tokens,
            cost_total_usd=row.cost_total_usd,
            evaluator_scores=row.evaluator_scores,
        )
