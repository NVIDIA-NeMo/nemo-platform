# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request/response schemas for the evaluator metrics API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from nemo_evaluator.shared.metric_bundles.bundles import (
    BundledMetricOutputSpec,
    MetricMetadata,
)
from nemo_evaluator_sdk.values.common import SecretRef
from nemo_platform_plugin.schema import DatetimeFilter, Filter
from pydantic import BaseModel, ConfigDict, Field


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


# Discriminated on ``kind`` so additional payload formats can join the union
# without changing the field type. Cloudpickle is the only kind today.
MetricPayload = Annotated[CloudpickleMetricPayload, Field(discriminator="kind")]


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


class MetricFilter(Filter):
    """Filter for metric queries."""

    workspace: str | None = Field(None, description="Filter by workspace.")
    name: str | None = Field(None, description="Filter by name.")
    metric_type: str | None = Field(None, description="Filter by metric type.")
    description: str | None = Field(None, description="Filter by description.")
    created_at: DatetimeFilter | None = Field(None, description="Filter by creation date.")
    updated_at: DatetimeFilter | None = Field(None, description="Filter by update date.")
