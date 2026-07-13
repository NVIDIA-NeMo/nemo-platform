# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minikube E2E coverage for the nemo-evaluator plugin.

These tests intentionally require an external platform deployment through
``NMP_BASE_URL``. Evaluator submit jobs compile to CPU task pods, so the durable
job path cannot be fully validated by the local subprocess harness.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path

import httpx
import pytest
from nemo_evaluator.sdk.job_resources import EvaluatorJobResource
from nemo_evaluator_sdk import ExactMatchMetric, InferenceParams, Model, ModelRef, RunConfig, RunConfigOnlineModel
from nemo_evaluator_sdk.enums import ModelFormat
from nemo_evaluator_sdk.values.results import EvaluationResult
from nemo_platform import APIStatusError, NeMoPlatform
from nmp.testing import add_mock_provider, short_unique_name, wait_for_model_entity
from nmp.testing.utils import ensure_passthrough_virtual_model

pytestmark = [
    pytest.mark.container_only,
    pytest.mark.timeout(1800),
]

EVALUATOR_JOB_TIMEOUT_SECONDS = 900.0
EVALUATOR_PENDING_TIMEOUT_SECONDS = 600.0
EVALUATOR_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_INTERNAL_PLATFORM_BASE_URL = "http://nemo-platform-api:8080"
IGW_ROUTE_TIMEOUT_SECONDS = 60.0
IGW_ROUTE_POLL_INTERVAL_SECONDS = 0.5
IGW_ROUTE_STABLE_SECONDS = 5.0
IGW_TRANSIENT_ROUTE_STATUSES = frozenset({404, 408, 425, 429, 500, 502, 503, 504})


def _exact_match_metric(*, candidate: str | None = "{{item.output}}") -> ExactMatchMetric:
    return ExactMatchMetric(reference="{{item.expected}}", candidate=candidate)


def _offline_rows() -> list[dict[str, str]]:
    return [
        {"input": "capital of France", "expected": "Paris", "output": "Paris"},
        {"input": "largest planet", "expected": "Jupiter", "output": "Saturn"},
    ]


def _chat_completion(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-evaluator-e2e",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }


def _string_headers(sdk: NeMoPlatform) -> dict[str, str]:
    return {key: value for key, value in sdk.default_headers.items() if isinstance(value, str)}


def _workspace_client(sdk: NeMoPlatform, workspace: str) -> NeMoPlatform:
    return NeMoPlatform(
        base_url=str(sdk.base_url).rstrip("/"),
        workspace=workspace,
        access_token=os.environ.get("NMP_ACCESS_TOKEN"),
        context_name=os.environ.get("NMP_CONTEXT_NAME"),
        max_retries=2,
        timeout=EVALUATOR_JOB_TIMEOUT_SECONDS,
        default_headers=_string_headers(sdk),
    )


def _assert_http_status(exc: BaseException, status_code: int) -> None:
    actual = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if actual is None and response is not None:
        actual = response.status_code
    assert actual == status_code


def _aggregate_score(result: EvaluationResult):
    for score in result.aggregate_scores.scores:
        if score.name.endswith("exact-match"):
            return score
    raise AssertionError(f"No exact-match aggregate score in {result.aggregate_scores.scores!r}")


def _row_score_values(result: EvaluationResult) -> list[float]:
    values: list[float] = []
    seen_score_names: list[str] = []
    rows = sorted(
        enumerate(result.row_scores),
        key=lambda indexed_row: indexed_row[1].row_index if indexed_row[1].row_index is not None else indexed_row[0],
    )
    for _, row in rows:
        for metric_scores in row.metrics.values():
            seen_score_names.extend(score.name for score in metric_scores)
            values.extend(float(score.value) for score in metric_scores if score.name.endswith("exact-match"))
    if not values:
        raise AssertionError(f"No exact-match row scores found. Saw score names: {seen_score_names!r}")
    return values


def _internal_model_route(workspace: str, model_name: str) -> str:
    base_url = os.environ.get("NMP_E2E_INTERNAL_BASE_URL", DEFAULT_INTERNAL_PLATFORM_BASE_URL).rstrip("/")
    return f"{base_url}/apis/inference-gateway/v2/workspaces/{workspace}/model/{model_name}/-/v1"


def _evaluator_url(sdk: NeMoPlatform, workspace: str, path: str) -> str:
    base_url = str(sdk.base_url).rstrip("/")
    return f"{base_url}/apis/evaluator/v2/workspaces/{workspace}/{path.lstrip('/')}"


def _raw_evaluator_post(sdk: NeMoPlatform, workspace: str, path: str, payload: dict[str, object]) -> httpx.Response:
    return sdk._client.post(
        _evaluator_url(sdk, workspace, path),
        json=payload,
        headers=_string_headers(sdk),
        timeout=sdk.timeout,
    )


def _wait_for_model_entity_route(sdk: NeMoPlatform, workspace: str, model_name: str) -> None:
    """Wait until IGW can route through the model-entity proxy path."""
    url = (
        f"{str(sdk.base_url).rstrip('/')}/apis/inference-gateway/v2/workspaces/{workspace}"
        f"/model/{model_name}/-/v1/chat/completions"
    )
    deadline = time.monotonic() + IGW_ROUTE_TIMEOUT_SECONDS
    stable_since: float | None = None
    last_status: int | None = None
    last_body = ""
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            response = sdk._client.post(
                url,
                json={"model": model_name, "messages": [{"role": "user", "content": "ping"}]},
                headers=_string_headers(sdk),
                timeout=10,
            )
        except httpx.RequestError as exc:
            stable_since = None
            last_error = repr(exc)
            time.sleep(IGW_ROUTE_POLL_INTERVAL_SECONDS)
            continue

        last_status = response.status_code
        last_body = response.text
        last_error = None
        if response.status_code == 200:
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= IGW_ROUTE_STABLE_SECONDS:
                return
            time.sleep(IGW_ROUTE_POLL_INTERVAL_SECONDS)
            continue
        stable_since = None
        if response.status_code in IGW_TRANSIENT_ROUTE_STATUSES:
            time.sleep(IGW_ROUTE_POLL_INTERVAL_SECONDS)
            continue
        response.raise_for_status()
    if stable_since is not None:
        stable_for = time.monotonic() - stable_since
        detail = (
            f"{last_status} {last_body[:500]} (stable for {stable_for:.1f}s; required {IGW_ROUTE_STABLE_SECONDS:.1f}s)"
        )
    else:
        detail = last_error if last_error is not None else f"{last_status} {last_body[:500]}"
    raise TimeoutError(
        f"Model entity route {workspace}/{model_name} was not ready after "
        f"{IGW_ROUTE_TIMEOUT_SECONDS}s. Last response: {detail}"
    )


def _cleanup_evaluator_job(sdk: NeMoPlatform, job_name: str) -> None:
    with suppress(Exception):
        sdk.jobs.cancel(name=job_name, workspace=sdk.workspace)
    with suppress(Exception):
        sdk.jobs.delete(name=job_name, workspace=sdk.workspace)


@pytest.fixture(scope="module")
def evaluator_workspace(sdk: NeMoPlatform) -> Iterator[str]:
    name = short_unique_name("e2e-eval")
    sdk.workspaces.create(name=name)
    try:
        yield name
    finally:
        with suppress(Exception):
            sdk.workspaces.delete(name)


@pytest.fixture(scope="module")
def evaluator_sdk(sdk: NeMoPlatform, evaluator_workspace: str) -> Iterator[NeMoPlatform]:
    client = _workspace_client(sdk, evaluator_workspace)
    try:
        yield client
    finally:
        with suppress(Exception):
            client.close()


@pytest.fixture(scope="module")
def completed_offline_job(evaluator_sdk: NeMoPlatform) -> Iterator[EvaluatorJobResource]:
    job = evaluator_sdk.evaluator.submit(
        metric=_exact_match_metric(),
        dataset=_offline_rows(),
        config=RunConfig(parallelism=1),
    )
    try:
        job.wait_until_done(
            poll_interval_seconds=EVALUATOR_POLL_INTERVAL_SECONDS,
            job_timeout_seconds=EVALUATOR_JOB_TIMEOUT_SECONDS,
            pending_timeout_seconds=EVALUATOR_PENDING_TIMEOUT_SECONDS,
        )
        yield job
    finally:
        _cleanup_evaluator_job(evaluator_sdk, job.name)


def test_health_check_through_minikube_ingress(sdk: NeMoPlatform) -> None:
    status = sdk.evaluator.plugin_status()

    assert status["plugin"] == "evaluator"
    assert status["status"] == "ok"
    assert "evaluator.evaluate" in status["jobs"]


def test_mock_provider_chat_completion_works_through_minikube_ingress(
    sdk: NeMoPlatform,
    evaluator_workspace: str,
) -> None:
    model_name = short_unique_name("eval-model")
    add_mock_provider(
        sdk,
        workspace=evaluator_workspace,
        name=model_name,
        mock_response_body=_chat_completion("Paris"),
    )

    response = sdk.inference.gateway.model.post(
        "v1/chat/completions",
        name=model_name,
        workspace=evaluator_workspace,
        body={"model": model_name, "messages": [{"role": "user", "content": "Capital of France?"}]},
    )

    assert response["choices"][0]["message"]["content"] == "Paris"


def test_metric_create_stores_inline_builtin_metric(evaluator_sdk: NeMoPlatform) -> None:
    name = short_unique_name("exact")
    try:
        metric = evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())

        assert metric.name == name
        assert metric.workspace == evaluator_sdk.workspace
        assert metric.metric_type == "exact-match"
        assert metric.payload_kind == "inline"
        assert metric.bundle_ref
    finally:
        with suppress(Exception):
            evaluator_sdk.evaluator.metrics.delete(name)


def test_metric_list_includes_created_metric(evaluator_sdk: NeMoPlatform) -> None:
    name = short_unique_name("exact")
    try:
        evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())

        listing = evaluator_sdk.evaluator.metrics.list(sort="-created_at")

        assert any(metric.name == name for metric in listing.data)
    finally:
        with suppress(Exception):
            evaluator_sdk.evaluator.metrics.delete(name)


def test_metric_list_filters_by_metric_type(evaluator_sdk: NeMoPlatform) -> None:
    name = short_unique_name("exact")
    try:
        evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())

        listing = evaluator_sdk.evaluator.metrics.list(metric_type="exact-match", page_size=100)

        assert any(metric.name == name for metric in listing.data)
        assert all(metric.metric_type == "exact-match" for metric in listing.data)
    finally:
        with suppress(Exception):
            evaluator_sdk.evaluator.metrics.delete(name)


def test_metric_retrieve_returns_stored_metric(evaluator_sdk: NeMoPlatform) -> None:
    name = short_unique_name("exact")
    try:
        created = evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())

        retrieved = evaluator_sdk.evaluator.metrics.retrieve(name)

        assert retrieved.id == created.id
        assert retrieved.name == name
        assert retrieved.metric_type == "exact-match"
        assert retrieved.payload_digest == created.payload_digest
    finally:
        with suppress(Exception):
            evaluator_sdk.evaluator.metrics.delete(name)


def test_metric_duplicate_create_is_rejected(evaluator_sdk: NeMoPlatform) -> None:
    name = short_unique_name("exact")
    try:
        evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())

        with pytest.raises((httpx.HTTPStatusError, APIStatusError)) as exc_info:
            evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())

        _assert_http_status(exc_info.value, 409)
    finally:
        with suppress(Exception):
            evaluator_sdk.evaluator.metrics.delete(name)


def test_metric_delete_removes_metric(evaluator_sdk: NeMoPlatform) -> None:
    name = short_unique_name("exact")
    created = False
    try:
        evaluator_sdk.evaluator.metrics.create(name, metric=_exact_match_metric())
        created = True

        evaluator_sdk.evaluator.metrics.delete(name)
        created = False

        with pytest.raises((httpx.HTTPStatusError, APIStatusError)) as exc_info:
            evaluator_sdk.evaluator.metrics.retrieve(name)
        _assert_http_status(exc_info.value, 404)
    finally:
        if created:
            with suppress(Exception):
                evaluator_sdk.evaluator.metrics.delete(name)


def test_offline_evaluate_job_completes_with_k8s_executor(completed_offline_job: EvaluatorJobResource) -> None:
    status = completed_offline_job.get_job_status()

    assert status.status == "completed"


def test_offline_evaluate_job_downloads_aggregate_and_row_scores(
    completed_offline_job: EvaluatorJobResource,
) -> None:
    result = completed_offline_job.get_result()

    aggregate = _aggregate_score(result)
    assert aggregate.count == 2
    assert aggregate.mean == 0.5
    assert _row_score_values(result) == [1.0, 0.0]


def test_offline_evaluate_job_downloads_artifacts(
    completed_offline_job: EvaluatorJobResource,
    tmp_path: Path,
) -> None:
    artifact_dir = completed_offline_job.download_artifacts(tmp_path)
    aggregate_files = list(artifact_dir.rglob("aggregate-scores.json"))
    row_score_files = list(artifact_dir.rglob("row-scores.jsonl"))

    assert aggregate_files, f"aggregate-scores.json missing under {artifact_dir}"
    assert row_score_files, f"row-scores.jsonl missing under {artifact_dir}"

    aggregate_payload = json.loads(aggregate_files[0].read_text(encoding="utf-8"))
    row_lines = [line for line in row_score_files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(score["name"].endswith("exact-match") for score in aggregate_payload["scores"])
    assert len(row_lines) == 2


def test_offline_evaluate_job_persists_queryable_eval_result(
    evaluator_sdk: NeMoPlatform,
    completed_offline_job: EvaluatorJobResource,
) -> None:
    result = evaluator_sdk.evaluator.eval_results.retrieve(completed_offline_job.name)
    by_job = evaluator_sdk.evaluator.eval_results.list(job_id=completed_offline_job.name)

    assert result.job_id == completed_offline_job.name
    assert result.metric_types == ["exact-match"]
    assert result.dataset_ref is None
    assert any(item.job_id == completed_offline_job.name for item in by_job.data)


def test_online_evaluate_job_uses_mock_provider_from_k8s_executor(
    sdk: NeMoPlatform,
    evaluator_sdk: NeMoPlatform,
    evaluator_workspace: str,
) -> None:
    model_name = short_unique_name("eval-model")
    add_mock_provider(
        sdk,
        workspace=evaluator_workspace,
        name=model_name,
        mock_response_body=_chat_completion("Paris"),
    )
    wait_for_model_entity(sdk, evaluator_workspace, model_name, ensure_virtual_model=True)
    ensure_passthrough_virtual_model(sdk, evaluator_workspace, model_name, timeout=IGW_ROUTE_TIMEOUT_SECONDS)
    _wait_for_model_entity_route(sdk, evaluator_workspace, model_name)
    target = Model(
        url=_internal_model_route(evaluator_workspace, model_name),
        name=model_name,
        format=ModelFormat.OPEN_AI,
    )

    job = evaluator_sdk.evaluator.submit(
        metric=_exact_match_metric(candidate=None),
        dataset=[{"question": "What is the capital of France?", "expected": "Paris"}],
        config=RunConfigOnlineModel(
            parallelism=1,
            request_timeout=60,
            max_retries=0,
            inference=InferenceParams(max_tokens=8),
        ),
        target=target,
        prompt_template={"messages": [{"role": "user", "content": "{{item.question}}"}]},
    )
    try:
        job.wait_until_done(
            poll_interval_seconds=EVALUATOR_POLL_INTERVAL_SECONDS,
            job_timeout_seconds=EVALUATOR_JOB_TIMEOUT_SECONDS,
            pending_timeout_seconds=EVALUATOR_PENDING_TIMEOUT_SECONDS,
        )

        result = job.get_result()

        aggregate = _aggregate_score(result)
        assert aggregate.count == 1
        assert aggregate.mean == 1.0
        assert result.row_scores[0].sample["output_text"] == "Paris"
    finally:
        _cleanup_evaluator_job(evaluator_sdk, job.name)


def test_missing_model_ref_is_rejected_before_submit(evaluator_sdk: NeMoPlatform) -> None:
    missing_model = f"{evaluator_sdk.workspace}/{short_unique_name('missing-model')}"

    with pytest.raises(ValueError, match="Model reference"):
        evaluator_sdk.evaluator.submit(
            metric=_exact_match_metric(candidate=None),
            dataset=[{"question": "What is the capital of France?", "expected": "Paris"}],
            config=RunConfigOnlineModel(parallelism=1),
            target=ModelRef(root=missing_model),
            prompt_template="{{item.question}}",
        )


def test_invalid_metric_ref_in_submit_is_rejected(evaluator_sdk: NeMoPlatform) -> None:
    payload = {
        "spec": {
            "metrics": [short_unique_name("missing-metric")],
            "dataset": _offline_rows(),
            "params": RunConfig(parallelism=1).model_dump(mode="json"),
        }
    }
    response = _raw_evaluator_post(evaluator_sdk, evaluator_sdk.workspace, "evaluate/jobs", payload)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        response.raise_for_status()

    _assert_http_status(exc_info.value, 422)


def test_invalid_metric_payload_is_rejected(evaluator_sdk: NeMoPlatform) -> None:
    payload = {
        "bundle_kind": "metric-bundle",
        "bundle_format_version": "v1",
        "metric_type": "exact-match",
        "metadata": {},
        "outputs": [{"name": "exact-match", "value_json_schema": {"type": "number"}}],
        "secrets": {},
        "payload": {"kind": "inline", "metric": {"reference": "{{item.expected}}"}},
    }
    response = _raw_evaluator_post(
        evaluator_sdk,
        evaluator_sdk.workspace,
        f"metrics/{short_unique_name('invalid')}",
        payload,
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        response.raise_for_status()

    _assert_http_status(exc_info.value, 422)


def test_nonexistent_evaluate_job_returns_not_found(evaluator_sdk: NeMoPlatform) -> None:
    with pytest.raises((httpx.HTTPStatusError, APIStatusError)) as exc_info:
        evaluator_sdk.evaluator.get_job_resource(short_unique_name("missing-job"))

    _assert_http_status(exc_info.value, 404)
