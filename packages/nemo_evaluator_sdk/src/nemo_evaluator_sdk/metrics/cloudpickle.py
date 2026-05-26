# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cloudpickle-backed metric bundle implementation."""

from __future__ import annotations

import hashlib
import pickle
import platform
from typing import Annotated, Literal

import cloudpickle
from nemo_evaluator_sdk.metrics.bundles import (
    BundledMetricOutputSpec,
    MetricBundle,
    MetricBundlePayload,
    MetricBundler,
    MetricBundlingError,
    metric_metadata,
    metric_secrets,
    register_metric_bundle_payload,
    register_metric_bundler,
    validate_metric_type,
)
from nemo_evaluator_sdk.metrics.protocol import Metric
from pydantic import ConfigDict, Field

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

    @classmethod
    def from_blob(cls, blob: bytes) -> CloudpickleMetricPayload:
        """Create a JSON-safe cloudpickle payload from raw bytes."""
        return cls(
            python_version=platform.python_version(),
            cloudpickle_version=cloudpickle.__version__,
            pickle_protocol=pickle.HIGHEST_PROTOCOL,
            blob=blob,
        )


class CloudpickleMetricBundler(MetricBundler):
    """Cloudpickle-backed metric bundler.

    Cloudpickle bundles execute arbitrary Python code when hydrated. This
    implementation is intended for explicit opt-in development/MVP use.
    """

    def bundle(self, metric: Metric) -> MetricBundle:
        """Serialize a runtime metric object to a cloudpickle bundle."""
        if not isinstance(metric, Metric):
            raise MetricBundlingError("object does not satisfy the Metric protocol")

        blob = cloudpickle.dumps(metric, protocol=pickle.HIGHEST_PROTOCOL)
        digest = hashlib.sha256(blob).hexdigest()
        return MetricBundle(
            metric_type=validate_metric_type(metric),
            metadata=metric_metadata(metric),
            outputs=[BundledMetricOutputSpec.from_output_spec(output) for output in metric.output_spec()],
            secrets=metric_secrets(metric),
            payload=CloudpickleMetricPayload.from_blob(blob),
            digest=digest,
        )

    def unbundle(self, metric: MetricBundle) -> Metric:
        """Hydrate a metric from a cloudpickle bundle."""
        payload = CloudpickleMetricPayload.model_validate(metric.payload.model_dump(mode="python"))
        blob = payload.blob
        digest = hashlib.sha256(blob).hexdigest()
        if digest != metric.digest:
            raise MetricBundlingError("metric bundle digest does not match payload")

        hydrated_metric = cloudpickle.loads(blob)
        if not isinstance(hydrated_metric, Metric):
            raise MetricBundlingError("unbundled object does not satisfy the Metric protocol")

        output_names = [output.name for output in hydrated_metric.output_spec()]
        bundled_output_names = [output.name for output in metric.outputs]
        if output_names != bundled_output_names:
            raise MetricBundlingError("unbundled metric output spec does not match bundle metadata")
        if validate_metric_type(hydrated_metric) != metric.metric_type:
            raise MetricBundlingError("unbundled metric type does not match bundle metadata")
        return hydrated_metric


register_metric_bundle_payload("cloudpickle", CloudpickleMetricPayload)
register_metric_bundler("cloudpickle", CloudpickleMetricBundler)
