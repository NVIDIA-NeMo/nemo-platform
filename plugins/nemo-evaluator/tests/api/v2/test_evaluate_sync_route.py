# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP route-level tests for the synchronous POST /evaluate endpoint.

Covers the happy-path offline evaluation, the security/limit guards (non-inline payloads,
network metrics, secret-bearing metrics, inline models, FilesetRef datasets, row/metric caps),
and the capacity machinery: 503 backpressure, 504 timeout, and slot release on true completion
even when the submitting request's event loop is gone (TestClient uses a loop per request).
"""

from __future__ import annotations

import threading
import time
from typing import Any

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
from nemo_evaluator_sdk.execution.values import EvaluationError
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.remote import RemoteMetric
from nemo_evaluator_sdk.values import Model
from nemo_evaluator_sdk.values.models import ModelRef
from nemo_evaluator_sdk.values.scores import JSONScoreParser, RangeScore, RemoteScore
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


@pytest.fixture
def fresh_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate slot state so capacity tests can't poison each other via the module global."""
    monkeypatch.setattr(evaluate_routes, "_SYNC_SLOTS", threading.BoundedSemaphore(1))


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
    # Network-backed metrics call a user-supplied URL (SSRF surface) — rejected. Built from a
    # real, self-consistent RemoteMetric bundle so this pins the route's network-type guard
    # itself, not the bundle-consistency backstop a mutated metric_type would trip instead.
    metric = RemoteMetric(
        url="http://attacker.test/score",
        body={"input": "{{item.expected}}"},
        scores=[RemoteScore(name="score")],
    )
    bundle = bundle_metric(metric, InlineMetricBundlePackager())
    body_metric = MetricInline.model_validate_json(bundle.model_dump_json()).model_dump(mode="json")
    body = {
        "metrics": [body_metric],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422
    assert "external endpoint" in resp.json()["detail"]


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


def test_sync_evaluate_rejects_over_cap_metrics(client: TestClient) -> None:
    metric_body = _metric_body(InlineMetricBundlePackager())
    body = {
        "metrics": [metric_body for _ in range(evaluate_routes.MAX_SYNC_METRICS + 1)],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422


def test_sync_evaluate_unknown_model_ref_returns_actionable_422(client: TestClient, mocker: MockerFixture) -> None:
    # Resolution failures are caller errors; the 422 must carry the resolver's message.
    class _CallerSdk:
        _custom_headers = {"X-NMP-Principal-Id": "user@example.com"}

    client.app.dependency_overrides[get_sdk_client] = _CallerSdk
    mocker.patch.object(
        PlatformModelResolver,
        "resolve_model",
        new=mocker.AsyncMock(side_effect=ValueError("Model reference 'default/judge' not found.")),
    )
    metric = LLMJudgeMetric(
        model=ModelRef(root="default/judge"),
        scores=[RangeScore(name="quality", minimum=0, maximum=4, parser=JSONScoreParser(json_path="quality"))],
        prompt_template={"messages": [{"role": "user", "content": "{{item.input}}"}]},
    )
    bundle = bundle_metric(metric, InlineMetricBundlePackager())
    body_metric = MetricInline.model_validate_json(bundle.model_dump_json()).model_dump(mode="json")

    resp = client.post(_BASE, json={"metrics": [body_metric], "dataset": [{"input": "hi"}]})

    assert resp.status_code == 422
    assert "default/judge" in resp.json()["detail"]


def test_sync_evaluate_worker_evaluation_error_returns_422_with_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _failing_run(**kwargs: object) -> object:
        raise EvaluationError(0, "dataset is missing required column 'expected'")

    monkeypatch.setattr(evaluate_routes, "run_evaluation", _failing_run)
    body = {
        "metrics": [_metric_body(InlineMetricBundlePackager())],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 422
    assert "missing required column" in resp.json()["detail"]


def test_sync_evaluate_worker_internal_bug_returns_500(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # A TypeError raised while executing is an internal bug, not a caller error: it must be a
    # 500 (visible to error-rate alerting), not a client-blaming 422.
    def _buggy_run(**kwargs: object) -> object:
        raise TypeError("'NoneType' object is not subscriptable")

    monkeypatch.setattr(evaluate_routes, "run_evaluation", _buggy_run)
    body = {
        "metrics": [_metric_body(InlineMetricBundlePackager())],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    resp = client.post(_BASE, json=body)

    assert resp.status_code == 500


def test_bound_worker_inference_caps_judge_and_ragas_call_time() -> None:
    # A detached worker's slot occupancy is bounded by its inference calls: judge metrics get a
    # wrapped inference fn, RAGAS metrics get request_timeout/max_retries inference extras.
    from nemo_evaluator_sdk.metrics.ragas import AnswerAccuracyMetric

    judge = LLMJudgeMetric(
        model=ModelRef(root="default/judge"),
        scores=[RangeScore(name="quality", minimum=0, maximum=4, parser=JSONScoreParser(json_path="quality"))],
        prompt_template={"messages": [{"role": "user", "content": "{{item.input}}"}]},
    )
    ragas = AnswerAccuracyMetric(judge_model=ModelRef(root="default/judge"))

    evaluate_routes._bound_worker_inference([judge, ragas], budget_seconds=60.0)

    assert judge._inference_fn is not None
    ragas_inference = ragas.inference.model_dump()
    assert ragas_inference["request_timeout"] == 60.0
    assert ragas_inference["max_retries"] == evaluate_routes._SYNC_WORKER_MAX_RETRIES


def test_bound_worker_inference_clamps_and_strips_ragas_transport() -> None:
    # Explicit oversized timeout/retries are clamped to the budget, and caller-supplied
    # transport/auth extras (SSRF / identity-forgery vector) are dropped from RAGAS inference.
    from nemo_evaluator_sdk.metrics.ragas import AnswerAccuracyMetric
    from nemo_evaluator_sdk.values.params import InferenceParams

    ragas = AnswerAccuracyMetric(
        judge_model=ModelRef(root="default/judge"),
        inference=InferenceParams.model_validate(
            {
                "request_timeout": 3600,
                "max_retries": 99,
                "temperature": 0.3,
                "base_url": "http://attacker.test/v1",
                "default_headers": {"X-NMP-Principal-Id": "attacker"},
            }
        ),
    )

    evaluate_routes._bound_worker_inference([ragas], budget_seconds=60.0)

    dumped = ragas.inference.model_dump()
    assert dumped["request_timeout"] == 60.0
    assert dumped["max_retries"] == evaluate_routes._SYNC_WORKER_MAX_RETRIES
    assert dumped["temperature"] == 0.3
    assert "base_url" not in dumped
    assert "default_headers" not in dumped


def test_sync_evaluate_error_responses_are_typed_in_openapi() -> None:
    # 422/503/504 bodies must carry a schema so generated clients get typed error detail.
    app = FastAPI()
    app.include_router(evaluate_routes.router, prefix="/v2/workspaces/{workspace}")
    responses = app.openapi()["paths"]["/v2/workspaces/{workspace}/evaluate"]["post"]["responses"]
    for code in ("422", "503", "504"):
        ref = responses[code]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/EvaluateSyncError")


def test_sync_evaluate_backpressure_timeout_and_slot_release(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fresh_slots: None
) -> None:
    """Full capacity lifecycle: 504 on timeout, 503 while the orphaned worker holds its slot,
    release on completion. TestClient's per-request loop also pins that release can't depend on
    the submitting loop (regression: a loop-coupled release leaked the slot until restart).
    """
    monkeypatch.setattr(evaluate_routes, "SYNC_EVALUATE_TIMEOUT_SECONDS", 0.2)
    gate = threading.Event()
    worker_is_daemon: list[bool] = []
    real_run_evaluation = evaluate_routes.run_evaluation

    def _gated_run(**kwargs: Any) -> object:
        worker_is_daemon.append(threading.current_thread().daemon)
        assert gate.wait(timeout=10), "test gate was never opened"
        return real_run_evaluation(**kwargs)

    monkeypatch.setattr(evaluate_routes, "run_evaluation", _gated_run)
    body = {
        "metrics": [_metric_body(InlineMetricBundlePackager())],
        "dataset": [{"expected": "yes", "output": "yes"}],
    }

    # 1. The eval outlives the sync budget: 504, worker detaches but keeps its slot.
    resp = client.post(_BASE, json=body)
    assert resp.status_code == 504

    # 2. The orphaned worker still holds the only slot: immediate 503, no queueing.
    resp = client.post(_BASE, json=body)
    assert resp.status_code == 503

    # 3. The worker finishes; its done callback must release the slot even though the
    #    request loop that submitted it is long gone.
    gate.set()
    deadline = time.monotonic() + 5
    while True:
        resp = client.post(_BASE, json=body)
        if resp.status_code == 200:
            break
        # 503 while the slot is still held; 504 possible if a probe itself outruns the
        # shortened budget on a slow machine — both mean "keep polling".
        assert resp.status_code in (503, 504), resp.text
        assert time.monotonic() < deadline, "slot was never released after worker completion"
        time.sleep(0.05)

    # Sync workers must be daemon threads so a stuck eval can't block process shutdown.
    assert worker_is_daemon and all(worker_is_daemon)
