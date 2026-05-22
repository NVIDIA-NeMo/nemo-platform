# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib

import pytest
from nemo_evaluator_sdk.metrics.base import (
    MetricBundle,
    MetricBundlingError,
)
from nemo_evaluator_sdk.metrics.cloudpickle import CloudpickleMetricBundler, CloudpickleMetricPayload
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import (
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)


class _CustomMetric:
    type = "custom-score"
    description = "custom metric"
    labels = {"source": "test"}

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])


class _NotMetric:
    pass


class _EmptyTypeMetric(_CustomMetric):
    type = ""


def test_cloudpickle_bundler_round_trips_builtin_metric() -> None:
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    bundler = CloudpickleMetricBundler()

    bundle = bundler.bundle(metric)
    hydrated = bundler.unbundle(bundle)

    assert bundle.metric_type == "exact-match"
    assert bundle.outputs[0].name == "exact-match"
    assert isinstance(hydrated, ExactMatchMetric)


def test_cloudpickle_bundler_round_trips_custom_protocol_metric() -> None:
    bundler = CloudpickleMetricBundler()

    bundle = bundler.bundle(_CustomMetric())
    serialized = bundle.model_dump_json()
    restored = MetricBundle.model_validate_json(serialized)
    hydrated = bundler.unbundle(restored)

    assert restored.bundle_kind == "metric-bundle"
    assert restored.metric_type == "custom-score"
    assert restored.metadata.description == "custom metric"
    assert restored.metadata.labels == {"source": "test"}
    assert restored.outputs[0].name == "score"
    assert isinstance(hydrated, _CustomMetric)


def test_cloudpickle_bundler_captures_digest_and_payload_metadata() -> None:
    bundle = CloudpickleMetricBundler().bundle(_CustomMetric())
    payload = CloudpickleMetricPayload.model_validate(bundle.payload)
    blob = payload.blob_bytes()

    assert bundle.digest == hashlib.sha256(blob).hexdigest()
    assert payload.kind == "cloudpickle"
    assert payload.python_version
    assert payload.cloudpickle_version
    assert payload.pickle_protocol > 0
    assert bundle.outputs[0].value_json_schema["title"] == "ContinuousScore"


def test_cloudpickle_bundler_rejects_non_metric_object() -> None:
    with pytest.raises(MetricBundlingError, match="Metric protocol"):
        CloudpickleMetricBundler().bundle(_NotMetric())  # type: ignore[arg-type]


def test_cloudpickle_bundler_rejects_empty_metric_type() -> None:
    with pytest.raises(MetricBundlingError, match="metric type must not be empty"):
        CloudpickleMetricBundler().bundle(_EmptyTypeMetric())


def test_cloudpickle_bundler_rejects_digest_mismatch() -> None:
    bundler = CloudpickleMetricBundler()
    bundle = bundler.bundle(_CustomMetric())
    corrupted = bundle.model_copy(update={"digest": "0" * 64})

    with pytest.raises(MetricBundlingError, match="digest"):
        bundler.unbundle(corrupted)
