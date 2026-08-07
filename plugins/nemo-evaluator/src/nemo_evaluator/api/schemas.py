# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request/response schemas for the evaluator API — metrics, eval results, and shared filters."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from nemo_evaluator.content_hash import DIGEST_PATTERN
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


# An entity reference is ``name`` or ``workspace/name``, each segment using the platform name charset.
# Shared by every ``workspace/name`` reference type (metrics, tasks). Enforced on the field so
# empty/malformed refs are rejected at validation rather than during parsing.
_ENTITY_REF_PATTERN = r"^[\w\-.]+(/[\w\-.]+)?$"

#: The charset a ``#fragment`` may use. Exported because anything that *mints* a fragment — notably
#: revision tag names — has to be constrained by it: a value outside this set can be stored happily
#: and then never appear in a reference, which is a silent dead end rather than an error.
REF_FRAGMENT_CHARSET = r"[\w\-.]+"

# A *sub-entity* reference adds an optional ``#fragment``, the platform's standard way of addressing
# something contained within an entity (filesets address a contained file the same way:
# ``workspace/fileset#path``). For a revisioned entity the fragment selects a revision — either a tag
# (``#latest``, ``#candidate``) or a full 64-char content digest.
#
# Deliberately a sibling of ``_ENTITY_REF_PATTERN`` rather than a widening of it: that constant is
# still shared by ``MetricRef``, which has no revisions, and admitting a fragment there would accept
# input nothing is built to resolve. ``TaskRef`` and ``TasksetRef`` both use this pattern, since both
# name revisioned records; ``MetricRef`` joins them when (if) metrics gain revisions.
_SUBENTITY_REF_PATTERN = rf"^[\w\-.]+(/[\w\-.]+)?(#{REF_FRAGMENT_CHARSET})?$"

#: The fragment separator for sub-entity references. Matches the fileset/job ref convention.
REF_FRAGMENT_SEPARATOR = "#"

#: The tag applied to every publish and used when a ref carries no fragment.
LATEST_TAG = "latest"


def parse_entity_ref(root: str, default_workspace: str) -> tuple[str, str]:
    """Split a validated ``workspace/name`` (or bare ``name``) reference into ``(workspace, name)``.

    The ``workspace/name`` vs bare-``name`` shape is guaranteed by the field's ``_ENTITY_REF_PATTERN``,
    so this only needs to split. Shared by every reference type (metrics, tasks); lives here — next to
    the pattern, with no entity dependency — so ref-owning modules can reuse it without cycling.

    Any ``#fragment`` is stripped before splitting, so callers that don't care about revisions keep
    working unchanged against a pinned ref. Use :func:`parse_subentity_ref` to read the fragment.
    """
    base, _, _ = root.partition(REF_FRAGMENT_SEPARATOR)
    workspace, separator, name = base.partition("/")
    if separator:
        return workspace, name
    return default_workspace, base


def parse_subentity_ref(root: str, default_workspace: str) -> tuple[str, str, str]:
    """Split a reference into ``(workspace, name, fragment)``.

    An absent fragment resolves to :data:`LATEST_TAG` — a bare ``workspace/name`` means "the current
    revision", never "unpinned". The fragment is returned verbatim: it may be a tag or a content
    digest, and telling them apart is resolution's job, not parsing's.
    """
    base, separator, fragment = root.partition(REF_FRAGMENT_SEPARATOR)
    workspace, name = parse_entity_ref(base, default_workspace)
    return workspace, name, fragment if separator and fragment else LATEST_TAG


class MetricRef(RootModel[str]):
    """Reference to a persisted metric (format: ``workspace/name`` or ``name``)."""

    root: str = Field(
        pattern=_ENTITY_REF_PATTERN,
        description="Reference to a stored metric (format: workspace/metric-name, or metric-name in the job workspace).",
    )


#: A wire metric is either an inline bundle DTO or a reference to a stored metric. Lives here (next to
#: ``MetricInline``) rather than in ``metric_refs`` so entity/DTO modules can use it without importing
#: the ref-resolution logic (which depends on ``entities`` and would cycle); ``metric_refs`` re-exports.
MetricRefOrInline: TypeAlias = MetricInline | MetricRef


class TaskRef(RootModel[str]):
    """Reference to a persisted task (format: ``workspace/name``, ``name``, or either with a
    ``#revision`` fragment).

    A taskset points at its member tasks by reference (there are no inline tasks), so a stored
    taskset only ever holds refs. Unlike :class:`MetricRef`, a task ref may address a specific
    revision via the platform's standard ``#`` sub-entity fragment.

    The fragment is optional *on input* and means :data:`LATEST_TAG` when absent — a bare
    ``workspace/name`` is "the current revision", not "unpinned". It may name a tag or a content
    digest. Anything **persisted** as a published snapshot must carry a resolved digest: tags move,
    and a stored tag fragment would silently re-point published membership.
    """

    root: str = Field(
        pattern=_SUBENTITY_REF_PATTERN,
        description="Reference to a stored task (format: workspace/task-name, or task-name in the "
        "taskset workspace), optionally pinned to a revision with '#<tag-or-digest>'.",
    )


class TasksetRef(RootModel[str]):
    """Reference to a persisted taskset (format: ``workspace/name`` or ``name``, optionally ``#rev``).

    Same shape and charset as :class:`TaskRef`. Lets an evaluation reference a stored taskset in place
    of an inline task list; the taskset's member tasks are loaded and expanded during spec resolution.

    An optional ``#`` fragment pins the taskset revision to expand — a tag or a full content digest,
    with an absent fragment meaning ``latest``.

    What each form guarantees, precisely. A taskset revision pins its members by digest, so a member
    task publishing new content never changes what *any* ref expands to. A **bare** ref still tracks
    the taskset's own revisions, and republishing the taskset re-resolves its members on write — so a
    ``replace`` can change both which members are named and the content they resolve to, even if the
    submitted member names were identical. A **pinned** ref is fixed against that too, and is what an
    evaluation needs to stay comparable across a ``replace``.
    """

    root: str = Field(
        pattern=_SUBENTITY_REF_PATTERN,
        description="Reference to a stored taskset (format: workspace/taskset-name, or taskset-name in the "
        "job workspace), optionally pinned to a revision with '#<tag-or-digest>'.",
    )


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
    revision: int = Field(
        description="Ordinal of the published revision this content corresponds to. Every stored task "
        "has at least one revision — creating a task publishes revision 1 — so this is never 0."
    )
    tags: dict[str, int] = Field(
        default_factory=dict,
        description="Tag → revision-ordinal pointers. Reading the record's current content returns "
        "every tag, including 'latest'. Reading a *specific* revision returns only the tags pointing "
        "at that revision, which may be none — so do not assume 'latest' is present.",
    )
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
    tags: list[str] = Field(
        default_factory=list,
        description="Tags to point at the revision this request publishes. 'latest' is always applied "
        "server-side and need not be listed.",
    )


class Revision(BaseModel):
    """A published revision of a task or taskset.

    Deliberately thin: it identifies a revision and says when it was cut, without repeating the
    content. Listing a record's history is a "what can I pin to?" question, and answering it with
    full content on every entry would make the response large for no benefit — fetch the record at
    a specific revision to get its content.
    """

    revision: int = Field(description="Monotonic 1-based ordinal within the record.")
    content_hash: str = Field(
        description="Full 64-char hex SHA-256 of the revision's content. This is what a pinned "
        "reference carries: 'workspace/name#<content_hash>'."
    )
    tags: list[str] = Field(default_factory=list, description="Tags currently pointing at this revision, if any.")
    created_at: datetime = Field(description="Timestamp the revision was published.")


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


def _reject_duplicate_task_refs(refs: list[TaskRef]) -> list[TaskRef]:
    """A taskset's members are an unordered set expressed as a list; a repeated ref is ambiguous
    (it can't mean anything more than membership), so reject duplicates at validation."""
    seen: set[str] = set()
    for ref in refs:
        if ref.root in seen:
            raise ValueError(f"duplicate task reference: {ref.root!r}")
        seen.add(ref.root)
    return refs


#: A list of task references with set semantics (order not significant, duplicates rejected).
TaskRefList: TypeAlias = Annotated[list[TaskRef], AfterValidator(_reject_duplicate_task_refs)]

#: Shape of a content digest in a ref fragment: full-length lowercase hex, never truncated.
_DIGEST_FRAGMENT_PATTERN = re.compile(DIGEST_PATTERN)


def _require_pinned_task_refs(refs: list[TaskRef]) -> list[TaskRef]:
    """Every member of a *published* taskset revision must name an exact content digest.

    Enforced on the field rather than in the publish path so it cannot be bypassed by any other
    writer. A ref that is bare (``workspace/name``) or tag-pinned (``#latest``, ``#candidate``)
    resolves through a mutable pointer: the moment that tag moves, the published revision's
    membership silently changes under it, and a "reproducible" dataset stops being reproducible.
    Tags are resolution *inputs*, resolved to digests at publish time; only digests persist.
    """
    for ref in refs:
        _, _, fragment = parse_subentity_ref(ref.root, "")
        if not _DIGEST_FRAGMENT_PATTERN.match(fragment):
            raise ValueError(
                f"task reference {ref.root!r} is not pinned to a content digest: a published taskset "
                f"revision must reference an exact revision (got fragment {fragment!r}). Tags move; "
                "resolve them to a digest before persisting."
            )
    return refs


#: Member refs of a published taskset revision: set semantics *and* every ref digest-pinned.
PinnedTaskRefList: TypeAlias = Annotated[
    list[TaskRef], AfterValidator(_reject_duplicate_task_refs), AfterValidator(_require_pinned_task_refs)
]


class Taskset(BaseModel):
    """API representation of a stored taskset — a flexible grouping of tasks with metadata.

    Members are referenced by ``workspace/name`` (there are no inline tasks). Membership is a set:
    order is not significant and duplicate references are rejected.
    """

    id: str = Field(description="Unique identifier for the stored taskset record.")
    name: str = Field(description="Taskset name — the stable id, unique within its workspace.")
    workspace: str = Field(description="Workspace the taskset belongs to.")
    project: str | None = Field(default=None, description="The project associated with this taskset.")
    description: str | None = Field(default=None, description="Human-readable description of the grouping.")
    tasks: TaskRefList = Field(
        default_factory=list, description="References to the member tasks (set semantics; duplicates rejected)."
    )
    metadata: TaskMetadataList = Field(default_factory=list, description="Key/value annotations for the taskset.")
    revision: int = Field(
        description="Ordinal of the published revision this content corresponds to. Every stored "
        "taskset has at least one revision, so this is never 0."
    )
    tags: dict[str, int] = Field(
        default_factory=dict,
        description="Tag → revision-ordinal pointers. Reading the record's current content returns "
        "every tag, including 'latest'. Reading a *specific* revision returns only the tags pointing "
        "at that revision, which may be none — so do not assume 'latest' is present.",
    )
    created_at: datetime = Field(description="Timestamp the taskset was created.")
    updated_at: datetime = Field(description="Timestamp the taskset was last updated.")


class TasksetInput(BaseModel):
    """Create/replace body for a stored taskset (the name comes from the path).

    The authorable subset of :class:`Taskset` — minus server-owned fields (id, name, workspace,
    timestamps).
    """

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, description="Human-readable description of the grouping.")
    tasks: TaskRefList = Field(
        default_factory=list,
        description="References to the member tasks (set semantics; duplicates rejected). Each may be "
        "bare, tag-pinned ('task-a#latest'), or digest-pinned; all are resolved to an exact digest "
        "when stored, so the grouping cannot change underneath you when a member republishes. "
        "Because membership is a set, the stored order is canonical rather than the submitted order: "
        "reordering the same members is not a content change and publishes no revision.",
    )
    metadata: TaskMetadataList = Field(default_factory=list, description="Key/value annotations for the taskset.")
    tags: list[str] = Field(
        default_factory=list,
        description="Tags to point at the revision this request publishes. 'latest' is always applied "
        "server-side and need not be listed.",
    )


class TasksetSort(StrEnum):
    """Sort fields for taskset queries."""

    NAME_ASC = "name"
    NAME_DESC = "-name"
    CREATED_AT_ASC = "created_at"
    CREATED_AT_DESC = "-created_at"
    UPDATED_AT_ASC = "updated_at"
    UPDATED_AT_DESC = "-updated_at"


class TasksetFilter(Filter):
    """Filter for taskset queries (top-level entity columns only; custom-field filtering is a follow-up)."""

    workspace: str | None = Field(None, description="Filter by workspace.")
    name: str | None = Field(None, description="Filter by name.")
    created_at: DatetimeFilter | None = Field(None, description="Filter by creation date.")
    updated_at: DatetimeFilter | None = Field(None, description="Filter by update date.")
