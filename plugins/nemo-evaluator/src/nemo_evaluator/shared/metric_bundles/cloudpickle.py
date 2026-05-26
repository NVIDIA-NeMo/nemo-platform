# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cloudpickle-backed metric bundle implementation."""

from __future__ import annotations

import hashlib
import pickle
import platform
from typing import Annotated, Literal

import cloudpickle
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundlePayload,
    MetricBundlingError,
    MetricPayloadBundler,
    register_metric_bundle_kind,
)
from nemo_evaluator_sdk.metrics.protocol import Metric
from pydantic import ConfigDict, Field, computed_field

NonEmptyBytes = Annotated[bytes, Field(min_length=1)]


class CloudpickleMetricPayload(MetricBundlePayload):
    """Cloudpickle payload for an executable metric object."""

    model_config = ConfigDict(extra="ignore", ser_json_bytes="base64", val_json_bytes="base64")

    python_version: str
    cloudpickle_version: str
    pickle_protocol: int
    blob: NonEmptyBytes

    @property
    def kind(self) -> Literal["cloudpickle"]:
        """Payload discriminator used by the metric bundle registry."""
        return "cloudpickle"

    @computed_field
    @property
    def digest(self) -> str:
        """Digest of the serialized metric payload."""
        return hashlib.sha256(bytes(self.blob)).hexdigest()

    @classmethod
    def from_blob(cls, blob: bytes) -> CloudpickleMetricPayload:
        """Create a JSON-safe cloudpickle payload from raw bytes."""
        return cls(
            python_version=platform.python_version(),
            cloudpickle_version=cloudpickle.__version__,
            pickle_protocol=pickle.HIGHEST_PROTOCOL,
            blob=blob,
        )


class CloudpickleMetricPayloadBundler(MetricPayloadBundler):
    """Cloudpickle-backed metric payload bundler.

    Cloudpickle bundles execute arbitrary Python code when hydrated. This
    implementation is intended for explicit opt-in development/MVP use.
    """

    def bundle(self, metric: Metric) -> MetricBundlePayload:
        """Serialize a runtime metric object to a cloudpickle payload."""
        if not isinstance(metric, Metric):
            raise MetricBundlingError("object does not satisfy the Metric protocol")

        blob = cloudpickle.dumps(metric, protocol=pickle.HIGHEST_PROTOCOL)
        return CloudpickleMetricPayload.from_blob(blob)

    def unbundle(self, payload: MetricBundlePayload) -> Metric:
        """Hydrate a metric from a cloudpickle payload."""
        cloudpickle_payload = CloudpickleMetricPayload.model_validate(payload.model_dump(mode="python"))
        hydrated_metric = cloudpickle.loads(cloudpickle_payload.blob)
        if not isinstance(hydrated_metric, Metric):
            raise MetricBundlingError("unbundled object does not satisfy the Metric protocol")
        return hydrated_metric


register_metric_bundle_kind(
    "cloudpickle",
    payload_type=CloudpickleMetricPayload,
    payload_bundler_factory=CloudpickleMetricPayloadBundler,
)
