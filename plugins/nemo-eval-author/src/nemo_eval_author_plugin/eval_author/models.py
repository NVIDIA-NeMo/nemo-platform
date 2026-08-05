# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared models for the top-level Eval Author."""

import math
import re
from collections.abc import Iterator, Mapping
from typing import Literal, Self, cast

from nemo_experimentalist_plugin.entities import DatasetRef, ResourceRef
from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, field_validator, model_validator
from pydantic_core import core_schema

_SHA256_IDENTITY_RE = re.compile(r"sha256:[0-9a-f]{64}")


class FrozenJsonObject(Mapping[str, object]):
    """Canonical immutable JSON object with ordinary JSON serialization."""

    __slots__ = ("_items",)
    _items: tuple[tuple[str, object], ...]

    def __init__(self, value: Mapping[object, object] | None = None) -> None:
        if value is None:
            value = {}
        if not isinstance(value, Mapping):
            raise ValueError("metadata must be a JSON object")
        object.__setattr__(self, "_items", _freeze_json_items(value))

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("FrozenJsonObject is immutable")

    def __getitem__(self, key: str) -> object:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenJsonObject):
            return self._items == other._items
        if isinstance(other, Mapping):
            try:
                return self == FrozenJsonObject(cast(Mapping[object, object], other))
            except (TypeError, ValueError):
                return False
        return False

    def to_json(self) -> dict[str, object]:
        """Return a detached mutable JSON value for serialization only."""
        return {key: _thaw_json(value) for key, value in self._items}

    @classmethod
    def _validate(cls, value: object) -> Self:
        if isinstance(value, cls):
            value = value.to_json()
        if not isinstance(value, Mapping):
            raise ValueError("metadata must be a JSON object")
        return cls(cast(Mapping[object, object], value))

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: object,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        del source_type, handler
        dictionary_schema = core_schema.dict_schema(
            keys_schema=core_schema.str_schema(),
            values_schema=core_schema.any_schema(),
        )
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            json_schema_input_schema=dictionary_schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda value: value.to_json(),
                return_schema=dictionary_schema,
            ),
        )


def _freeze_json_items(value: Mapping[object, object]) -> tuple[tuple[str, object], ...]:
    items: list[tuple[str, object]] = []
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("metadata JSON object keys must be strings")
        items.append((key, _freeze_json(item)))
    return tuple(sorted(items))


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        return FrozenJsonObject(cast(Mapping[object, object], value))
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    raise ValueError(f"metadata contains non-JSON value of type {type(value).__name__}")


def _thaw_json(value: object) -> object:
    if isinstance(value, FrozenJsonObject):
        return value.to_json()
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


class InsightRef(ResourceRef):
    """Serializable reference to the Insight that drives authoring."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    metadata: FrozenJsonObject = Field(default_factory=FrozenJsonObject)


class ReadOnlyDatasetRef(DatasetRef):
    """Frozen DatasetRef copy safe to expose as authoring context."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    metadata: FrozenJsonObject = Field(default_factory=FrozenJsonObject)


def _copy_dataset_ref(value: object) -> object:
    if isinstance(value, DatasetRef):
        return value.model_dump(mode="python")
    return value


class EvalAuthorEvaluationContext(BaseModel):
    """Split-agnostic, read-only references used while authoring evaluations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_template: ReadOnlyDatasetRef = Field(
        description="Task-template dataset reference used for new task materialization."
    )
    reference_task_sets: tuple[ReadOnlyDatasetRef, ...] = Field(
        description=(
            "Read-only existing task-set references used for duplicate detection and verifier/metric conventions. "
            "Their optimizer split labels have no meaning to Eval Author."
        )
    )

    @field_validator("task_template", mode="before")
    @classmethod
    def _copy_task_template(cls, value: object) -> object:
        return _copy_dataset_ref(value)

    @field_validator("reference_task_sets", mode="before")
    @classmethod
    def _copy_reference_task_sets(cls, value: object) -> object:
        if isinstance(value, list | tuple):
            return tuple(_copy_dataset_ref(reference) for reference in value)
        return value


class EvalAuthorRequest(BaseModel):
    """CLI-safe logical input to an Eval Author run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight: InsightRef
    evaluation_context: EvalAuthorEvaluationContext

    @field_validator("insight", mode="before")
    @classmethod
    def _copy_insight(cls, value: object) -> object:
        if isinstance(value, ResourceRef):
            return value.model_dump(mode="python")
        return value


class ArtifactDescriptor(BaseModel):
    """Content-addressed artifact returned across the Eval Author boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uri: str = Field(description="Portable locator for the authored artifact.")
    identity: str = Field(description="Content-addressed SHA-256 identity of the artifact.")

    @field_validator("uri")
    @classmethod
    def _validate_uri(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("artifact URI must be non-empty")
        return value

    @field_validator("identity")
    @classmethod
    def _validate_identity(cls, value: str) -> str:
        if _SHA256_IDENTITY_RE.fullmatch(value) is None:
            raise ValueError("artifact identity must use sha256:<64 lowercase hex characters>")
        return value


class AuthoredMetric(BaseModel):
    """One portable metric promised by an authored verifier patch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(description="Non-empty key emitted by the verifier.")
    description: str = Field(description="Human-readable behavior measured by this metric.")
    runtime_evidence: tuple[str, ...] = Field(
        min_length=1,
        description="Runtime artifacts the verifier must inspect rather than inferred or fabricated evidence.",
    )
    scale: Literal["unit_interval"] = Field(
        default="unit_interval",
        description="Metric values are constrained to the inclusive [0.0, 1.0] interval.",
    )
    direction: Literal["higher_is_better"] = Field(
        default="higher_is_better",
        description="Larger metric values always represent better behavior.",
    )

    @field_validator("key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("metric key must be non-empty")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("metric description must be non-empty")
        return value

    @field_validator("runtime_evidence")
    @classmethod
    def _validate_runtime_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("runtime evidence entries must be non-empty")
        return normalized


class AuthoredMetricContract(BaseModel):
    """Unique metric declarations emitted together by one authored verifier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: tuple[AuthoredMetric, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_keys(self) -> Self:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for metric in self.metrics:
            if metric.key in seen:
                duplicates.add(metric.key)
            seen.add(metric.key)
        if duplicates:
            duplicate_text = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate metric key(s): {duplicate_text}")
        return self

    @property
    def keys(self) -> tuple[str, ...]:
        """Return metric keys in declared order."""
        return tuple(metric.key for metric in self.metrics)


class MetricAuthoringResult(BaseModel):
    """Structured response from the CodeAct metric-authoring method."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_contract: AuthoredMetricContract
    summary: str

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("metric authoring summary must be non-empty")
        return value


class EvalAuthorConfig(BaseModel):
    """Tuning parameters for the Eval Author agent."""

    max_summary_tokens: int = Field(
        default=80_000,
        description="Max tokens the token-budget summarizer may use.",
    )
    max_traces: int = Field(
        default=10,
        description="Max trace refs from the insight to analyze in depth.",
    )
    max_validation_repair_attempts: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Max Eval Author repair attempts after mandatory Insight verifier validation fails.",
    )


class EvalAuthorResult(BaseModel):
    """CLI-safe artifacts produced by one Eval Author run.

    A run with no usable trace references has all three artifact fields set to
    ``None``. It never returns mutable source datasets as a passthrough.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_set: ArtifactDescriptor | None = Field(
        default=None,
        description="Content-addressed authored task-set artifact, or None when no artifact was authored.",
    )
    verifier_patch: ArtifactDescriptor | None = Field(
        default=None,
        description="Portable verifier-patch artifact, or None until one was produced.",
    )
    metric_contract: AuthoredMetricContract | None = Field(
        default=None,
        description="Metrics emitted by the verifier patch, or None when no artifact was authored.",
    )
    summary: str

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Eval Author result summary must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_artifact_relationships(self) -> Self:
        if self.task_set is None:
            if self.verifier_patch is not None or self.metric_contract is not None:
                raise ValueError("verifier_patch and metric_contract require a task_set artifact")
            return self
        if self.metric_contract is None:
            raise ValueError("an authored task_set requires a metric_contract")
        return self

    @classmethod
    def no_artifacts(cls, summary: str) -> Self:
        """Return an explicit successful result that produced no artifacts."""
        return cls(
            task_set=None,
            verifier_patch=None,
            metric_contract=None,
            summary=summary,
        )


# Short aliases keep downstream annotations readable while the authored names
# make ownership explicit at the CLI boundary.
MetricContract = AuthoredMetricContract
MetricContractEntry = AuthoredMetric
