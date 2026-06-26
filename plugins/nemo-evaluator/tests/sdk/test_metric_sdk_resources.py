# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the client.evaluator.metrics SDK resources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from nemo_evaluator.api.schemas import Metric
from nemo_evaluator.sdk.metric_resources import (
    AsyncEvaluatorMetricsResource,
    EvaluatorMetricsResource,
)
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundle,
    MetricBundlePackagerPolicyError,
    bundle_metric,
)
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import Metric as RuntimeMetric
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult


class _CustomRuntimeMetric:
    """A protocol-satisfying metric that is not inline-bundleable."""

    type = "custom-score"
    description = "custom metric"
    labels: dict[str, str] = {}

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])


def _bundle() -> MetricBundle:
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    return bundle_metric(metric, CloudpickleMetricBundlePackager())


def _metric_response(name: str, bundle: MetricBundle) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return Metric(
        id=f"metric_bundle-{name}",
        name=name,
        workspace="default",
        metric_type=bundle.metric_type,
        description=bundle.metadata.description,
        labels=bundle.metadata.labels,
        outputs=bundle.outputs,
        secrets=bundle.secrets,
        payload_kind=bundle.payload.kind,
        payload_digest=bundle.payload.digest,
        bundle_ref=f"default/metric-bundle.{name}#bundle.json",
        created_at=now,
        updated_at=now,
    ).model_dump(mode="json")


def _response(payload: dict[str, Any]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _platform(http_client: Any) -> MagicMock:
    platform = MagicMock()
    platform._client = http_client
    platform.base_url = "http://localhost:8080"
    platform.workspace = "default"
    platform.default_headers = {}
    platform.timeout = 30
    return platform


# ---- sync ------------------------------------------------------------------


def test_sync_create_posts_bundle_and_returns_metric() -> None:
    bundle = _bundle()
    http_client = MagicMock()
    http_client.post.return_value = _response(_metric_response("exact", bundle))
    resource = EvaluatorMetricsResource(_platform(http_client))

    result = resource.create("exact", metric=bundle)

    assert result.name == "exact"
    url, kwargs = http_client.post.call_args[0], http_client.post.call_args.kwargs
    # Name is in the path; the body is the bare MetricInline.
    assert url[0] == "http://localhost:8080/apis/evaluator/v2/workspaces/default/metrics/exact"
    body = kwargs["json"]
    assert body["metric_type"] == bundle.metric_type
    assert body["payload"]["kind"] == "cloudpickle"


def test_sync_create_defaults_to_inline_for_builtin_metric() -> None:
    bundle = _bundle()
    http_client = MagicMock()
    http_client.post.return_value = _response(_metric_response("exact", bundle))
    resource = EvaluatorMetricsResource(_platform(http_client))
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")

    resource.create("exact", metric=metric)

    body = http_client.post.call_args.kwargs["json"]
    assert body["payload"]["kind"] == "inline"


def test_sync_create_requires_explicit_packager_for_custom_metric() -> None:
    resource = EvaluatorMetricsResource(_platform(MagicMock()))

    with pytest.raises(MetricBundlePackagerPolicyError, match="CloudpickleMetricBundlePackager"):
        resource.create("custom", metric=cast(RuntimeMetric, _CustomRuntimeMetric()))


def test_sync_retrieve_targets_item_url() -> None:
    bundle = _bundle()
    http_client = MagicMock()
    http_client.get.return_value = _response(_metric_response("exact", bundle))
    resource = EvaluatorMetricsResource(_platform(http_client))

    resource.retrieve("exact")

    assert http_client.get.call_args[0][0] == "http://localhost:8080/apis/evaluator/v2/workspaces/default/metrics/exact"


def test_sync_list_returns_data_items() -> None:
    bundle = _bundle()
    http_client = MagicMock()
    http_client.get.return_value = _response({"data": [_metric_response("a", bundle), _metric_response("b", bundle)]})
    resource = EvaluatorMetricsResource(_platform(http_client))

    result = resource.list()

    assert {m.name for m in result.data} == {"a", "b"}


def test_sync_delete_issues_delete_request() -> None:
    http_client = MagicMock()
    http_client.delete.return_value = _response({})
    resource = EvaluatorMetricsResource(_platform(http_client))

    resource.delete("exact")

    assert (
        http_client.delete.call_args[0][0] == "http://localhost:8080/apis/evaluator/v2/workspaces/default/metrics/exact"
    )


# ---- async -----------------------------------------------------------------


async def test_async_create_posts_bundle_and_returns_metric() -> None:
    bundle = _bundle()
    http_client = MagicMock()
    http_client.post = AsyncMock(return_value=_response(_metric_response("exact", bundle)))
    resource = AsyncEvaluatorMetricsResource(_platform(http_client))

    result = await resource.create("exact", metric=bundle, workspace="ws1")

    assert result.name == "exact"
    assert http_client.post.call_args[0][0] == "http://localhost:8080/apis/evaluator/v2/workspaces/ws1/metrics/exact"
