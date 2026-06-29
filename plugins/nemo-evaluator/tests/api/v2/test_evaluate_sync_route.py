# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP route-level tests for the synchronous POST /evaluate endpoint.

Covers the happy-path offline evaluation plus the security/limit guards: cloudpickle metrics,
network (remote) metrics, secret-bearing metrics, inline (non-ModelRef) models, FilesetRef
datasets, and over-cap inline datasets are all rejected with 422.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.api.v2 import evaluate as evaluate_routes
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundlePackager, bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator.shared.metric_bundles.inline import InlineMetricBundlePackager
from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.values import Model
from nemo_evaluator_sdk.values.models import ModelRef
from nemo_evaluator_sdk.values.scores import JSONScoreParser, RangeScore
from nemo_platform_plugin.dependencies import get_sdk_client
from pytest_mock import MockerFixture

_BASE = "/v2/workspaces/default/evaluate"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(evaluate_routes.router, prefix="/v2/workspaces/{workspace}")
    # Offline built-in metrics never touch the SDK client.
    app.dependency_overrides[get_sdk_client] = lambda: None
    return TestClient(app)


def _metric_body(packager: MetricBundlePackager) -> dict:
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    bundle = bundle_metric(metric, packager)
    return MetricInline.model_validate_json(bundle.model_dump_json()).model_dump(mode="json")


def _llm_judge_inline_model_body() -> dict:
    """An LLM-judge metric whose judge model is an inline Model (not a ModelRef)."""
    metric = LLMJudgeMetric(
        model=Model(url="http://example.test/v1/chat/completions", name="judge"),
        scores=[
            RangeScore(
                name="quality",
                description="quality score",
                minimum=0,
                maximum=4,
                parser=JSONScoreParser(json_path="quality"),
            )
        ],
        prompt_template={"messages": [{"role": "user", "content": "{{item.input}}"}]},
    )
    bundle = bundle_metric(metric, InlineMetricBundlePackager())
    return MetricInline.model_validate_json(bundle.model_dump_json()).model_dump(mode="json")


def test_sync_evaluate_offline_returns_scores(client: TestClient) -> None:
    body = {
        "metrics": [_metric_body(InlineMetricBundlePackager())],
        "dataset": [
            {"expected": "yes", "output": "yes"},
            {"expected": "yes", "output": "no"},
        ],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "aggregate_scores" in payload
    assert len(payload["row_scores"]) == 2


def test_sync_evaluate_rejects_cloudpickle_metric(client: TestClient) -> None:
    body = {
        "metrics": [_metric_body(CloudpickleMetricBundlePackager())],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422


def test_sync_evaluate_rejects_network_backed_metric(client: TestClient) -> None:
    # Network-backed metrics call a user-supplied URL (SSRF surface) — rejected.
    body_metric = _metric_body(InlineMetricBundlePackager())
    body_metric["metric_type"] = "remote"
    body = {
        "metrics": [body_metric],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422


def test_sync_evaluate_rejects_metric_with_secrets(client: TestClient) -> None:
    # Secret references would be resolved from the API-process env — exfil vector, rejected.
    body_metric = _metric_body(InlineMetricBundlePackager())
    body_metric["secrets"] = {"api_key": "NVIDIA_API_KEY"}
    body = {
        "metrics": [body_metric],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422


def test_sync_evaluate_rejects_inline_model(client: TestClient) -> None:
    # Inline models carry an arbitrary URL (SSRF) — only platform ModelRefs allowed.
    body = {
        "metrics": [_llm_judge_inline_model_body()],
        "dataset": [{"input": "hi", "output": "hello"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422


def test_sync_evaluate_llm_judge_modelref_forwards_caller_headers(client: TestClient, mocker: MockerFixture) -> None:
    # LLM-judge with a ModelRef judge: the resolved model reaches inference with the caller's headers.
    class _CallerSdk:
        _custom_headers = {"X-NMP-Principal-Id": "user@example.com"}

    client.app.dependency_overrides[get_sdk_client] = _CallerSdk

    mocker.patch.object(
        PlatformModelResolver,
        "resolve_model",
        new=mocker.AsyncMock(
            return_value=Model(
                url="http://igw.local/v1/chat/completions", name="resolved-judge", format=ModelFormat.OPEN_AI
            )
        ),
    )

    captured: dict = {}

    async def _fake_inference(model: Model, request: dict, max_retries: int | None = 3, **kwargs: object) -> dict:
        captured["headers"] = dict(model.default_headers or {})
        return {"choices": [{"message": {"content": '{"quality": 3}'}}]}

    mocker.patch("nemo_evaluator_sdk.inference.make_inference_request", new=_fake_inference)

    metric = LLMJudgeMetric(
        model=ModelRef(root="default/judge"),
        scores=[RangeScore(name="quality", minimum=0, maximum=4, parser=JSONScoreParser(json_path="quality"))],
        prompt_template={"messages": [{"role": "user", "content": "{{item.input}}"}]},
    )
    bundle = bundle_metric(metric, InlineMetricBundlePackager())
    body_metric = MetricInline.model_validate_json(bundle.model_dump_json()).model_dump(mode="json")
    body = {"metrics": [body_metric], "dataset": [{"input": "hi", "output": "hello"}]}

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 200, resp.text
    # The resolved judge model reached the inference call carrying the caller's principal header.
    assert captured["headers"] == {"X-NMP-Principal-Id": "user@example.com"}
    assert len(resp.json()["row_scores"]) == 1


def test_sync_evaluate_rejects_fileset_ref_dataset(client: TestClient) -> None:
    body = {
        "metrics": [_metric_body(InlineMetricBundlePackager())],
        "dataset": "default/my-fileset",  # not inline rows
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422


def test_sync_evaluate_rejects_over_cap_dataset(client: TestClient) -> None:
    body = {
        "metrics": [_metric_body(InlineMetricBundlePackager())],
        "dataset": [{"expected": "a", "output": "a"} for _ in range(11)],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422
