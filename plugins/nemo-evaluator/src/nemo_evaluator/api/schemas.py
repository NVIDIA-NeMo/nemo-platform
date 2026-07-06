# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request/response schemas for the evaluator API — metrics, eval results, and shared filters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from nemo_evaluator.shared.metric_bundles.bundles import (
    BundledMetricOutputSpec,
    MetricMetadata,
)
from nemo_evaluator_sdk.agent_eval.tasks import SemanticView
from nemo_evaluator_sdk.values.common import SecretRef
from nemo_evaluator_sdk.values.results import AggregatedMetricResult
from nemo_platform_plugin.api.filter import ComparisonOperation, FilterOperation, LogicalOperation
from nemo_platform_plugin.api.parsed_filter import ENTITY_BASE_FIELDS
from nemo_platform_plugin.schema import DatetimeFilter, Filter
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, RootModel, field_validator


class DataFilter(Filter):
    """A ``Filter`` whose declared non-base fields are stored under the entity's ``data.*`` column.

    Implements the duck-typed hooks ``make_filter_dep`` looks for, so a custom-field filter (e.g.
    ``metric_type`` or ``job_id``) is rewritten to ``data.<field>`` for the entity store. The plain
    ``Filter`` does no translation, so an un-prefixed custom field reaches the store unresolved and
    500s. (The richer ``nmp.common`` filter does this, but plugins can't depend on it — minimal port.)
    """

    @classmethod
    def _get_entity_field_map(cls) -> dict[str, str]:
        return {name: f"data.{name}" for name in cls.model_fields if name not in ENTITY_BASE_FIELDS}

    @classmethod
    def translate_operation(cls, operation: FilterOperation) -> FilterOperation:
        field_map = cls._get_entity_field_map()

        def _walk(op: FilterOperation) -> FilterOperation:
            if isinstance(op, ComparisonOperation):
                mapped = field_map.get(op.field)
                return op if mapped is None else op.model_copy(update={"field": mapped})
            if isinstance(op, LogicalOperation):
                return op.model_copy(update={"operations": [_walk(child) for child in op.operations]})
            return op

        return _walk(operation)


class CloudpickleMetricPayload(BaseModel):
    """Wire schema for a cloudpickle-serialized metric payload.

    Mirrors the runtime ``CloudpickleMetricPayload`` so the API contract is
    explicit in the OpenAPI spec. The runtime bundle model serializes payloads
    polymorphically (typed as an abstract base), which renders as an opaque
    object in the spec; this concrete DTO documents the actual fields.
    """

    model_config = ConfigDict(extra="forbid", ser_json_bytes="base64", val_json_bytes="base64")

    kind: Literal["cloudpickle"] = Field(description="Payload format discriminator.")
    python_version: str = Field(description="Python version the metric was pickled with (must match at execution).")
    cloudpickle_version: str = Field(description="cloudpickle version used to serialize the metric.")
    pickle_protocol: int = Field(description="Pickle protocol used.")
    blob: bytes = Field(description="Base64-encoded cloudpickled metric object.")
    digest: str | None = Field(
        default=None,
        description="SHA-256 digest of the payload bytes. Informational; recomputed server-side.",
    )


class InlineMetricPayload(BaseModel):
    """Wire schema for an inline (config-serialized) metric payload.

    Mirrors the runtime ``InlineMetricPayload``. The metric is stored as its own
    JSON configuration and reconstructed from the metric type union at execution,
    so no code is shipped or executed on load. Used for platform-recognized
    built-in metric types.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["inline"] = Field(description="Payload format discriminator.")
    metric: dict[str, Any] = Field(
        description="JSON-serialized built-in metric configuration, discriminated by its own `type`."
    )
    digest: str | None = Field(
        default=None,
        description="SHA-256 digest of the canonical metric JSON. Informational; recomputed server-side.",
    )

    @field_validator("metric")
    @classmethod
    def _metric_must_declare_type(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject payloads without a metric ``type`` discriminator at the API boundary.

        The metric body stays an open object (the concrete shape is validated when
        the bundle is hydrated against the metric type union), but a non-empty
        ``type`` is required so malformed payloads fail fast rather than at execution.
        """
        metric_type = value.get("type")
        if not isinstance(metric_type, str) or not metric_type:
            raise ValueError("inline metric payload must include a non-empty 'type'")
        return value


# Discriminated on ``kind`` so additional payload formats can join the union
# without changing the field type.
MetricPayload = Annotated[CloudpickleMetricPayload | InlineMetricPayload, Field(discriminator="kind")]


class MetricInline(BaseModel):
    """An executable metric submitted to the platform.

    Carries the bundled metric — type, metadata, output contracts, secret
    references, and a format-specific payload — used both as the create-request
    body and as an inline metric in an evaluation job.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_kind: Literal["metric-bundle"] = "metric-bundle"
    bundle_format_version: Literal["v1"] = "v1"
    metric_type: str = Field(min_length=1, description="Runtime metric type name.")
    metadata: MetricMetadata = Field(default_factory=MetricMetadata, description="User-facing metric metadata.")
    outputs: list[BundledMetricOutputSpec] = Field(min_length=1, description="The metric's output contracts.")
    secrets: dict[str, SecretRef] = Field(
        default_factory=dict, description="Secret references required to execute the metric."
    )
    payload: MetricPayload = Field(description="Format-specific serialized metric.")


# A reference is ``name`` or ``workspace/name``, each segment using the platform name charset.
# Enforced on the field so empty/malformed refs are rejected at validation rather than during parsing.
_METRIC_REF_PATTERN = r"^[\w\-.]+(/[\w\-.]+)?$"


class MetricRef(RootModel[str]):
    """Reference to a persisted metric (format: ``workspace/name`` or ``name``)."""

    root: str = Field(
        pattern=_METRIC_REF_PATTERN,
        description="Reference to a stored metric (format: workspace/metric-name, or metric-name in the job workspace).",
    )


#: A wire metric is either an inline bundle DTO or a reference to a stored metric. Lives here (next to
#: ``MetricInline``) rather than in ``metric_refs`` so entity/DTO modules can use it without importing
#: the ref-resolution logic (which depends on ``entities`` and would cycle); ``metric_refs`` re-exports.
MetricRefOrInline: TypeAlias = MetricInline | MetricRef


class Metric(BaseModel):
    """API representation of a stored metric.

    The canonical executable bundle lives in the Files service; the fields here
    are the queryable projection plus the reference and digest needed to load it.
    """

    id: str = Field(description="Unique identifier for the stored metric.")
    name: str = Field(description="Name of the metric, unique within its workspace.")
    workspace: str = Field(description="Workspace the metric belongs to.")
    project: str | None = Field(default=None, description="The project associated with this metric.")
    metric_type: str = Field(description="Runtime metric type name.")
    description: str | None = Field(default=None, description="Description captured from the metric's metadata.")
    labels: dict[str, str] = Field(default_factory=dict, description="Labels captured from the metric's metadata.")
    outputs: list[BundledMetricOutputSpec] = Field(description="The metric's output contracts.")
    secrets: dict[str, SecretRef] = Field(description="Secret references required to execute the metric.")
    payload_kind: str = Field(description="Payload discriminator of the stored bundle.")
    payload_digest: str = Field(description="Digest of the stored payload.")
    bundle_ref: str = Field(description="Files reference to the canonical serialized bundle.")
    derived: bool = Field(
        default=False,
        description="True for a content-addressed metric auto-stored from an inline task metric "
        "(excluded from the default metric listing).",
    )
    created_at: datetime = Field(description="Timestamp the metric was created.")
    updated_at: datetime = Field(description="Timestamp the metric was last updated.")


class MetricSort(StrEnum):
    """Sort fields for metric queries."""

    NAME_ASC = "name"
    NAME_DESC = "-name"
    CREATED_AT_ASC = "created_at"
    CREATED_AT_DESC = "-created_at"
    UPDATED_AT_ASC = "updated_at"
    UPDATED_AT_DESC = "-updated_at"


class MetricFilter(DataFilter):
    """Filter for metric queries."""

    workspace: str | None = Field(None, description="Filter by workspace.")
    name: str | None = Field(None, description="Filter by name.")
    metric_type: str | None = Field(None, description="Filter by metric type.")
    description: str | None = Field(None, description="Filter by description.")
    derived: bool | None = Field(None, description="Filter by derived flag.")
    created_at: DatetimeFilter | None = Field(None, description="Filter by creation date.")
    updated_at: DatetimeFilter | None = Field(None, description="Filter by update date.")


# --- Eval result DTOs --------------------------------------------------------
#
# API representation of the persisted result records (the storage entities are
# ``AgentEvalResultEntity`` / ``EvaluateResultEntity``). A separate DTO — like ``Metric`` for
# ``MetricBundleEntity`` — so the wire/SDK contract round-trips cleanly: an ``EntityBase``'s
# ``id`` / ``created_at`` / ``updated_at`` are computed/output-only and don't deserialize from
# the entity's own serialized form, whereas these plain fields do.


class _ResultBase(BaseModel):
    """Fields common to both result DTOs (provenance + aggregated scores + target traits)."""

    id: str = Field(description="Unique identifier for the stored result record.")
    name: str = Field(description="Result record name (equals the producing job's id).")
    workspace: str = Field(description="Workspace the result belongs to.")
    project: str | None = Field(default=None, description="The project associated with this result.")
    job_id: str = Field(description="Identifier of the job run that produced this result.")
    # Nullable traits default to None so they round-trip when the list route serializes with
    # response_model_exclude_none (which drops null values from the payload) — matching ``Metric``.
    target_kind: str | None = Field(
        default=None, description="Target discriminator: 'model', 'agent', or a runner kind."
    )
    target_name: str | None = Field(default=None, description="Model/agent entity name, or the runner's model.")
    target_url: str | None = Field(default=None, description="Endpoint URL, when the target is an HTTP model/agent.")
    scores: AggregatedMetricResult = Field(description="Aggregated metric scores for the run.")
    bundle_ref: str = Field(description="Reference to the full result bundle in the Files service.")
    created_at: datetime = Field(description="Timestamp the result was created.")
    updated_at: datetime = Field(description="Timestamp the result was last updated.")


class AgentEvalResult(_ResultBase):
    """API representation of a persisted agent-evaluation result record."""


class EvaluateResult(_ResultBase):
    """API representation of a persisted (row) evaluation result record."""

    dataset_ref: str | None = Field(
        default=None, description="Reference to the dataset evaluated; None for an inline dataset."
    )
    metric_types: list[str] = Field(description="Runtime metric type names applied in the run.")


class TaskInputs(BaseModel):
    """A task's recognized input fields.

    ``extra="forbid"``: only the field below is accepted. ``instruction`` is the agent's prompt; the
    runtime falls back to the task ``intent`` when it is unset.
    """

    model_config = ConfigDict(extra="forbid")

    instruction: str | None = Field(
        default=None, description="The agent's instruction (its prompt). Falls back to the task `intent` when unset."
    )


class MetadataItem(BaseModel):
    """A single key/value annotation on a task."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Annotation key.")
    value: str = Field(description="Annotation value.")


def _reject_duplicate_metadata_keys(items: list[MetadataItem]) -> list[MetadataItem]:
    """Metadata is a key→value map expressed as a list; duplicate keys would silently collapse (e.g.
    when folded into a mapping for the runtime), so reject them at validation rather than lose data."""
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise ValueError(f"duplicate metadata key: {item.key!r}")
        seen.add(item.key)
    return items


#: A task's metadata: key/value annotations with unique keys (duplicates rejected at validation).
TaskMetadataList: TypeAlias = Annotated[list[MetadataItem], AfterValidator(_reject_duplicate_metadata_keys)]


class Task(BaseModel):
    """API representation of a stored agent-eval task.

    Maps to the SDK :class:`~nemo_evaluator_sdk.agent_eval.tasks.AgentEvalTask` — the task's stable
    ``id`` is the record ``name`` (unique within its workspace). Metrics are stored in their wire form
    (inline bundles and/or references to stored metrics); references resolve to inline at run time.
    """

    id: str = Field(description="Unique identifier for the stored task record.")
    name: str = Field(description="Task name — the stable task id, unique within its workspace.")
    workspace: str = Field(description="Workspace the task belongs to.")
    project: str | None = Field(default=None, description="The project associated with this task.")
    intent: str = Field(description="Human-readable description of the desired agent behavior.")
    inputs: TaskInputs = Field(default_factory=TaskInputs, description="The task's recognized input fields.")
    metrics: list[MetricRef] = Field(
        default_factory=list,
        description="References to the metrics that score this task; inline metrics submitted on create "
        "are normalized to (derived) stored metrics, so a stored task holds refs only.",
    )
    views: dict[str, SemanticView] = Field(
        default_factory=dict, description="Optional reporting views mapping metric outputs into named semantic scores."
    )
    metadata: TaskMetadataList = Field(default_factory=list, description="Key/value annotations for the task.")
    created_at: datetime = Field(description="Timestamp the task was created.")
    updated_at: datetime = Field(description="Timestamp the task was last updated.")


class TaskInput(BaseModel):
    """Create/replace body for a stored task (the name comes from the path).

    The authorable subset of :class:`Task` — the SDK ``AgentEvalTask`` shape minus server-owned
    fields (id, name, workspace, timestamps).
    """

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(description="Human-readable description of the desired agent behavior.")
    inputs: TaskInputs = Field(default_factory=TaskInputs, description="The task's recognized input fields.")
    metrics: list[MetricRefOrInline] = Field(
        default_factory=list, description="Metrics that score this task — inline bundles and/or stored-metric refs."
    )
    views: dict[str, SemanticView] = Field(
        default_factory=dict, description="Optional reporting views mapping metric outputs into named semantic scores."
    )
    metadata: TaskMetadataList = Field(default_factory=list, description="Key/value annotations for the task.")


class TaskSort(StrEnum):
    """Sort fields for task queries."""

    NAME_ASC = "name"
    NAME_DESC = "-name"
    CREATED_AT_ASC = "created_at"
    CREATED_AT_DESC = "-created_at"
    UPDATED_AT_ASC = "updated_at"
    UPDATED_AT_DESC = "-updated_at"


class TaskFilter(Filter):
    """Filter for task queries (top-level entity columns only; custom-field filtering is a follow-up)."""

    workspace: str | None = Field(None, description="Filter by workspace.")
    name: str | None = Field(None, description="Filter by name.")
    created_at: DatetimeFilter | None = Field(None, description="Filter by creation date.")
    updated_at: DatetimeFilter | None = Field(None, description="Filter by update date.")
