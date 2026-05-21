# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime protocol for implementing Evaluator metrics."""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from nemo_platform.beta.evaluator.values.common import SecretRef
from pydantic import BaseModel, ConfigDict, Field, RootModel, field_serializer, field_validator

SecretResolver = Callable[[str], Awaitable[str | None]]


class DatasetRow(BaseModel):
    """Original dataset row plus optional stable row identity."""

    model_config = ConfigDict(extra="forbid")

    row_index: int | None = None
    data: dict[str, Any]


class CandidateOutput(BaseModel):
    """Candidate or prediction output being scored for one dataset row."""

    model_config = ConfigDict(extra="forbid")

    output_text: str | None = None
    response: Any | None = None
    trajectory: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_sample(self) -> dict[str, Any]:
        """Return a sample-shaped payload for template rendering helpers."""
        sample = dict(self.metadata)
        if self.output_text is not None:
            sample["output_text"] = self.output_text
        if self.response is not None:
            sample["response"] = self.response
        if self.trajectory is not None:
            sample["trajectory"] = self.trajectory
        return sample


class MetricInput(BaseModel):
    """Complete per-row scoring input passed to a metric."""

    model_config = ConfigDict(extra="forbid")

    row: DatasetRow
    candidate: CandidateOutput


class ContinuousScore(RootModel[float]):
    """Continuous numeric metric value."""


class DiscreteScore(RootModel[int]):
    """Discrete numeric metric value."""


class Label(RootModel[str]):
    """String label metric value."""


class BooleanValue(RootModel[bool]):
    """Boolean metric value."""


class MetricOutputSpec(BaseModel):
    """Schema for one named value emitted by a metric."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str
    description: str | None = None
    value_schema: type[BaseModel]

    @field_validator("name")
    @classmethod
    def _name_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("metric output name must not be empty")
        return value

    @staticmethod
    def continuous_score(name: str, description: str | None = None) -> "MetricOutputSpec":
        return MetricOutputSpec(name=name, description=description, value_schema=ContinuousScore)

    @staticmethod
    def discrete_score(name: str, description: str | None = None) -> "MetricOutputSpec":
        return MetricOutputSpec(name=name, description=description, value_schema=DiscreteScore)

    @staticmethod
    def label(name: str, description: str | None = None) -> "MetricOutputSpec":
        return MetricOutputSpec(name=name, description=description, value_schema=Label)

    @staticmethod
    def boolean(name: str, description: str | None = None) -> "MetricOutputSpec":
        return MetricOutputSpec(name=name, description=description, value_schema=BooleanValue)

    @staticmethod
    def model(name: str, value_schema: type[BaseModel], description: str | None = None) -> "MetricOutputSpec":
        return MetricOutputSpec(name=name, description=description, value_schema=value_schema)

    def coerce_value(self, value: Any) -> BaseModel:
        """Validate and coerce a raw output value to this spec's declared schema."""
        return self.value_schema.model_validate(value)

    def coerce_output(self, output: "MetricOutput") -> BaseModel:
        """Validate and coerce a named metric output against this spec."""
        if output.name != self.name:
            raise ValueError(f"Expected metric output {self.name!r}, got {output.name!r}")
        return self.coerce_value(output.value)

    def value_json_schema(self) -> dict[str, Any]:
        return self.value_schema.model_json_schema()


class MetricDescriptor(BaseModel):
    """Metadata describing a metric implementation and its declared outputs."""

    model_config = ConfigDict(extra="forbid")

    type: str
    outputs: list[MetricOutputSpec] = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def _type_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("metric type must not be empty")
        return value

    @field_validator("outputs")
    @classmethod
    def _output_names_must_be_unique(cls, value: list[MetricOutputSpec]) -> list[MetricOutputSpec]:
        names = [output.name for output in value]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate metric output names: {duplicates}")
        return value


class MetricOutput(BaseModel):
    """One named value emitted by a metric."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: Any

    @field_serializer("value")
    def serialize_nan(self, value: Any) -> Any:
        if isinstance(value, float) and math.isnan(value):
            return "NaN"
        return value


class MetricResult(BaseModel):
    """Structured row-level metric result."""

    model_config = ConfigDict(extra="forbid")

    outputs: list[MetricOutput]


@runtime_checkable
class Metric(Protocol):
    """Shared row-scoring primitive for SDK runtime metrics."""

    @property
    def type(self) -> str:
        """Return the public metric key/type identifier."""
        ...

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return declared row-level outputs emitted by this metric."""
        ...

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute structured output for one row/candidate pair."""
        ...


@runtime_checkable
class CorpusMetric(Protocol):
    """Protocol for metrics that also emit corpus-level scores."""

    async def compute_corpus_scores(self, inputs: list[MetricInput]) -> MetricResult | None:
        """Compute corpus-level scores across all evaluated rows."""
        ...


@runtime_checkable
class MetricWithSecrets(Protocol):
    """Protocol for metrics that require secrets."""

    def secrets(self) -> dict[str, SecretRef]:
        """Return environment variables mapped to secret references."""
        ...

    async def resolve_secrets(self, secret_resolver: SecretResolver) -> None:
        """Resolve secrets before the metric is used for evaluation."""
        ...


@runtime_checkable
class MetricWithPreflight(Protocol):
    """Protocol for metrics that need one-time setup before parallel evaluation starts."""

    async def preflight(self) -> None:
        """Run one-time preflight before processing rows."""
        ...


def validate_metric_result(result: MetricResult, outputs: list[MetricOutputSpec]) -> MetricResult:
    """Validate a metric result against its declared outputs."""
    returned_names = [output.name for output in result.outputs]
    duplicates = sorted({name for name in returned_names if returned_names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Duplicate metric output names: {duplicates}")

    outputs_by_name = {output.name: output for output in outputs}
    declared_names = [output.name for output in outputs]
    declared = set(declared_names)
    returned = set(returned_names)
    missing = [name for name in declared_names if name not in returned]
    undeclared = [name for name in returned_names if name not in declared]

    if missing:
        raise ValueError(f"Missing declared metric outputs: {missing}")
    if undeclared:
        raise ValueError(f"Undeclared metric outputs: {undeclared}")
    for output in result.outputs:
        outputs_by_name[output.name].coerce_output(output)
    return result
