# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP route-level tests for the read-only /metric-types and evaluate-schema routes.

Asserts the REST surface is sourced from the same `metric_catalog` helpers the
CLI uses (single source of truth) and that schemas match the Pydantic models.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_evaluator.api.v2 import catalog as catalog_routes
from nemo_evaluator.api.v2.evaluate import EvaluateSyncRequest
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec
from nemo_evaluator.metric_catalog import metric_type_entries, metric_type_models


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    # Mirror production mounting: catalog routes are workspace-independent at /v2.
    app.include_router(catalog_routes.router, prefix="/v2")
    return TestClient(app)


def test_list_metric_types_matches_catalog(client: TestClient) -> None:
    resp = client.get("/v2/metric-types")
    assert resp.status_code == 200
    # Single source of truth: REST output is exactly the shared catalog helper,
    # which is the same function the `nemo evaluator metric-types` CLI prints.
    assert resp.json() == {"metric_types": metric_type_entries()}


def test_get_metric_type_schema_matches_model(client: TestClient) -> None:
    # Pick a known built-in metric type from the catalog rather than hardcoding.
    metric_type, model_cls = next(iter(metric_type_models().items()))

    resp = client.get(f"/v2/metric-types/{metric_type}")

    assert resp.status_code == 200
    assert resp.json() == model_cls.model_json_schema()


def test_get_metric_type_schema_unknown_returns_404(client: TestClient) -> None:
    resp = client.get("/v2/metric-types/not-a-real-metric")
    assert resp.status_code == 404


def test_list_metric_types_response_is_typed() -> None:
    # The OpenAPI schema must expose the envelope (metric_types with name/description
    # entries) so generated SDK clients get typed accessors, not a free-form map.
    app = FastAPI()
    app.include_router(catalog_routes.router, prefix="/v2")
    schema = app.openapi()["paths"]["/v2/metric-types"]["get"]["responses"]["200"]
    response_ref = schema["content"]["application/json"]["schema"]["$ref"]
    assert response_ref.endswith("/MetricTypeList")


def test_get_evaluate_schema_matches_sync_request_model(client: TestClient) -> None:
    # /evaluate/schema sits beside POST .../evaluate, so it must describe that route's body.
    resp = client.get("/v2/evaluate/schema")
    assert resp.status_code == 200
    assert resp.json() == EvaluateSyncRequest.model_json_schema()


def test_get_evaluate_jobs_schema_matches_job_input_spec(client: TestClient) -> None:
    resp = client.get("/v2/evaluate/jobs/schema")
    assert resp.status_code == 200
    assert resp.json() == EvaluateInputSpec.model_json_schema()
