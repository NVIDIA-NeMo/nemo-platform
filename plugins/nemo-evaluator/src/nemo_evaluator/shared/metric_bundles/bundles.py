# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend-neutral metric bundle models and protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal, Protocol, cast

from nemo_evaluator_sdk.metrics.protocol import (
    BooleanValue,
    ContinuousScore,
    DiscreteScore,
    Label,
    Metric,
    MetricOutputSpec,
    MetricWithSecrets,
)
from nemo_evaluator_sdk.values.common import SecretRef
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

BundleMetricTypeName = Annotated[str, StringConstraints(min_length=1)]


class MetricBundlingError(ValueError):
    """Raised when a metric cannot be bundled or hydrated."""


class MetricMetadata(BaseModel):
    """User-facing metadata captured with a bundled metric."""

    model_config = ConfigDict(extra="allow", revalidate_instances="never")

    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class BundledMetricOutputSpec(BaseModel):
    """JSON-safe projection of a runtime metric output spec."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    value_kind: Literal["continuous", "discrete", "label", "boolean", "model"] = "model"
    value_json_schema: dict[str, Any]

    @classmethod
    def from_output_spec(cls, output: MetricOutputSpec) -> BundledMetricOutputSpec:
        """Capture the serializable contract for one runtime output."""
        return cls(
            name=output.name,
            description=output.description,
            value_kind=_output_value_kind(output),
            value_json_schema=output.value_json_schema(),
        )


def _output_value_kind(output: MetricOutputSpec) -> Literal["continuous", "discrete", "label", "boolean", "model"]:
    if issubclass(output.value_schema, ContinuousScore):
        return "continuous"
    if issubclass(output.value_schema, DiscreteScore):
        return "discrete"
    if issubclass(output.value_schema, Label):
        return "label"
    if issubclass(output.value_schema, BooleanValue):
        return "boolean"
    return "model"


class MetricBundlePayload(BaseModel, ABC):
    """Base class for concrete Pydantic metric bundle payloads."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Payload discriminator used to select the bundler implementation."""
        ...


_PAYLOAD_TYPES: dict[str, type[MetricBundlePayload]] = {}
_BUNDLER_FACTORIES: dict[str, Callable[[], MetricBundler]] = {}


def _payload_kind(payload: MetricBundlePayload) -> str:
    kind = payload.kind
    if not kind:
        raise MetricBundlingError("metric bundle payload kind must not be empty")
    return kind


def register_metric_bundle_payload(kind: str, payload_type: type[MetricBundlePayload]) -> None:
    """Register a concrete Pydantic payload model for a bundle kind."""
    if not kind:
        raise ValueError("metric bundle payload kind must not be empty")
    _PAYLOAD_TYPES[kind] = payload_type


def register_metric_bundler(kind: str, factory: Callable[[], MetricBundler]) -> None:
    """Register a metric bundler factory for a payload kind."""
    if not kind:
        raise ValueError("metric bundle payload kind must not be empty")
    _BUNDLER_FACTORIES[kind] = factory


class MetricBundle(BaseModel):
    """Standalone executable metric bundle entity used by backend execution."""

    model_config = ConfigDict(extra="forbid")

    bundle_kind: Literal["metric-bundle"] = "metric-bundle"
    bundle_format_version: Literal["v1"] = "v1"
    metric_type: BundleMetricTypeName
    metadata: MetricMetadata = Field(default_factory=MetricMetadata)
    outputs: list[BundledMetricOutputSpec] = Field(min_length=1)
    secrets: dict[str, SecretRef] = Field(default_factory=dict)
    payload: SerializeAsAny[MetricBundlePayload]
    digest: str

    @field_serializer("payload")
    def _serialize_payload(self, payload: MetricBundlePayload) -> dict[str, Any]:
        value = payload.model_dump(mode="json")
        value["kind"] = _payload_kind(payload)
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_must_have_kind(cls, value: object) -> object:
        if isinstance(value, MetricBundlePayload):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("metric bundle payload must be an object")
        payload_data = cast(Mapping[str, object], value)
        kind = payload_data.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValueError("metric bundle payload must include a non-empty kind")
        payload_type = _PAYLOAD_TYPES.get(kind)
        if payload_type is None:
            raise ValueError(f"unsupported metric bundle payload kind: {kind}")
        return payload_type.model_validate(value)

    @model_validator(mode="after")
    def _output_names_must_be_unique(self) -> MetricBundle:
        names = [output.name for output in self.outputs]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate metric output names: {duplicates}")
        return self


class MetricBundler(Protocol):
    """Interface for metric bundle implementations."""

    def bundle(self, metric: Metric) -> MetricBundle:
        """Serialize an executable metric to a bundle entity."""
        ...

    def unbundle(self, metric: MetricBundle) -> Metric:
        """Hydrate an executable metric from a bundle entity."""
        ...


def metric_bundler_for_payload(payload: MetricBundlePayload) -> MetricBundler:
    """Create the bundler registered for a metric bundle payload."""
    kind = _payload_kind(payload)
    factory = _BUNDLER_FACTORIES.get(kind)
    if factory is None:
        raise MetricBundlingError(f"unsupported metric bundle payload kind: {kind}")
    return factory()


def validate_metric_type(metric: Metric) -> str:
    """Return the runtime metric type after validating the protocol contract."""
    value = metric.type
    if not isinstance(value, str):
        raise MetricBundlingError("metric type must be a string")
    if not value:
        raise MetricBundlingError("metric type must not be empty")
    return value


def metric_metadata(metric: Metric) -> MetricMetadata:
    """Capture optional runtime metric metadata."""
    description = getattr(metric, "description", None)
    if description is not None and not isinstance(description, str):
        raise MetricBundlingError("metric description must be a string when provided")

    raw_labels = getattr(metric, "labels", None) or {}
    if not isinstance(raw_labels, Mapping):
        raise MetricBundlingError("metric labels must be a mapping when provided")
    labels = dict(raw_labels)
    return MetricMetadata(description=description, labels=labels)


def metric_secrets(metric: Metric) -> dict[str, SecretRef]:
    """Capture secret environment mappings needed to execute one metric."""
    if not isinstance(metric, MetricWithSecrets):
        return {}
    return metric.secrets()
