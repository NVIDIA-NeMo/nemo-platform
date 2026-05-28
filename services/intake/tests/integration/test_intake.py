# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the Intake service route surface."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from nemo_platform import NeMoPlatform
from nmp.intake.service import IntakeService
from nmp.testing.client import create_test_client


@pytest.fixture(scope="module")
def http_client() -> Generator[TestClient, None, None]:
    """TestClient with IntakeService."""
    with create_test_client(
        IntakeService,
        client_type=TestClient,
    ) as client:
        yield client


@pytest.fixture(scope="module")
def sdk(http_client: TestClient) -> NeMoPlatform:
    """SDK client backed by the test client."""
    return NeMoPlatform(base_url="http://testserver", http_client=http_client)


def test_intake_openapi_keeps_span_era_routes(sdk: NeMoPlatform) -> None:
    response = sdk._client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json().get("paths", {})

    assert "/apis/intake/v2/workspaces/{workspace}/spans" in paths
    assert "get" in paths["/apis/intake/v2/workspaces/{workspace}/spans"]
    assert "/apis/intake/v2/workspaces/{workspace}/spans/{span_id}" in paths
    assert "get" in paths["/apis/intake/v2/workspaces/{workspace}/spans/{span_id}"]
    assert "/apis/intake/v2/workspaces/{workspace}/traces" in paths
    assert "get" in paths["/apis/intake/v2/workspaces/{workspace}/traces"]
    assert "/apis/intake/v2/workspaces/{workspace}/traces/{id}" in paths
    assert "get" in paths["/apis/intake/v2/workspaces/{workspace}/traces/{id}"]
    assert "/apis/intake/v2/workspaces/{workspace}/annotations" in paths
    assert "/apis/intake/v2/workspaces/{workspace}/evaluator-results" in paths
    assert "/apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces" in paths


def test_intake_openapi_removes_legacy_entry_app_task_and_export_routes(sdk: NeMoPlatform) -> None:
    response = sdk._client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json().get("paths", {})

    legacy_paths = {
        "/apis/intake/v2/workspaces/{workspace}/apps",
        "/apis/intake/v2/workspaces/{workspace}/apps/{name}",
        "/apis/intake/v2/workspaces/{workspace}/apps/{name}/tasks",
        "/apis/intake/v2/workspaces/{workspace}/apps/{app}/tasks/{name}",
        "/apis/intake/v2/workspaces/{workspace}/entries",
        "/apis/intake/v2/workspaces/{workspace}/entries/{name}",
        "/apis/intake/v2/workspaces/{workspace}/entries/{name}/events",
        "/apis/intake/v2/workspaces/{workspace}/entries/{entry}/events/{name}",
        "/apis/intake/v2/workspaces/{workspace}/export/jobs",
        "/apis/intake/v2/workspaces/{workspace}/export/jobs/{name}",
        "/apis/intake/v2/workspaces/{workspace}/export/preview",
    }

    assert legacy_paths.isdisjoint(paths)
