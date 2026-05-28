# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for auth header propagation.

These tests verify that when a user makes a request to the evaluator service,
the user's auth credentials are properly forwarded to internal service calls
(entities service, jobs service, etc.).
"""

from typing import Generator
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from nmp.core.files.service import FilesService
from nmp.core.jobs.service import JobsService
from nmp.evaluator.service import EvaluatorService
from nmp.testing.access_log import AccessLog
from nmp.testing.client import ClientContext, create_test_client

# Test user credentials
TEST_USER_EMAIL = "test-user@example.com"
TEST_USER_HEADERS = {
    "X-NMP-Principal-Id": TEST_USER_EMAIL,
    "X-NMP-Principal-Email": TEST_USER_EMAIL,
}

SERVICE_PRINCIPAL = "service:integration-test"
SERVICE_HEADERS = {
    "X-NMP-Principal-Id": SERVICE_PRINCIPAL,
}


def _require_access_log(ctx: ClientContext) -> AccessLog:
    assert ctx.access_log is not None
    return ctx.access_log


class TestAuthHeaderPropagation:
    """Tests that verify auth headers are propagated to internal service calls."""

    @pytest.fixture(scope="class")
    def test_client_with_auth(self) -> Generator[TestClient, None, None]:
        """Create test client with auth enabled and multiple services."""
        with create_test_client(
            EvaluatorService,
            JobsService,
            FilesService,
            client_type=TestClient,
            auth_enabled=True,
            workspaces=["default", "test-workspace"],
            projects=["default/test-project"],
        ) as client:
            yield client

    def test_metrics_list_forwards_user_headers(self, test_client_with_auth: TestClient):
        """Test that listing metrics forwards user auth headers to entity store.

        When a user requests metrics, the evaluator should forward the user's
        auth headers when querying the entity store for metrics.
        """
        # Make request as authenticated user
        response = test_client_with_auth.get(
            "/apis/evaluation/v2/workspaces/default/metrics",
            headers=TEST_USER_HEADERS,
        )

        # The request should succeed (user has access to default workspace)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_metrics_list_denied_without_auth(self, test_client_with_auth: TestClient):
        """Test that listing metrics without auth headers is denied."""
        response = test_client_with_auth.get("/apis/evaluation/v2/workspaces/default/metrics")

        # Should be denied - no auth headers
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"

    def test_service_principal_can_access_metrics(self, test_client_with_auth: TestClient):
        """Test that service principals can access metrics."""
        response = test_client_with_auth.get(
            "/apis/evaluation/v2/workspaces/default/metrics",
            headers=SERVICE_HEADERS,
        )

        # Service principals should have access
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestAuthHeaderPropagationWithAccessLog:
    """Tests that verify auth headers are propagated using the access_log feature.

    These tests use the access_log feature to capture all HTTP requests processed
    by the app, then verify that internal SDK calls contain the expected auth headers.
    """

    @pytest.fixture(scope="class")
    def test_context(self) -> Generator[ClientContext, None, None]:
        """Create test client with auth and access_log enabled."""
        with create_test_client(
            EvaluatorService,
            JobsService,
            FilesService,
            client_type=ClientContext,
            auth_enabled=True,
            access_log=True,
            workspaces=["default"],
            projects=["default/test-project"],
        ) as ctx:
            yield ctx

    def test_metrics_endpoint_propagates_user_headers_to_entities(self, test_context: ClientContext):
        """Verify that entity service calls use service principal with on-behalf-of delegation.

        The /apis/evaluation/v2/workspaces/.../metrics endpoint queries the entity store to fetch metrics.
        Internal entity requests authenticate as service:evaluation and include
        X-NMP-Principal-On-Behalf-Of with the original user's ID for audit attribution.

        Note: We filter for /entities/metric requests specifically, excluding:
        - /entities/role_binding: Used by auth service policy refresh (uses service:auth)
        """
        access_log = _require_access_log(test_context)
        access_log.clear()

        test_principal = "specific-user@example.com"

        response = test_context.test_client.get(
            "/apis/evaluation/v2/workspaces/default/metrics",
            headers={
                "X-NMP-Principal-Id": test_principal,
                "X-NMP-Principal-Email": test_principal,
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        metric_entity_requests = access_log.filter(
            path_contains="/entities/metric",
            method="GET",
        )

        assert len(metric_entity_requests) > 0, (
            f"Expected internal metric entity requests. Captured paths: {[r.path for r in access_log.requests]}"
        )

        for req in metric_entity_requests:
            assert req.principal_id == "service:evaluation", (
                f"Expected service:evaluation as principal in internal request to {req.path}, got: {req.principal_id}"
            )
            assert req.on_behalf_of == test_principal, (
                f"Expected X-NMP-Principal-On-Behalf-Of={test_principal} in internal request "
                f"to {req.path}, got: {req.on_behalf_of}"
            )

    def test_different_users_have_different_principals_in_internal_calls(self, test_context: ClientContext):
        """Verify that different users' on-behalf-of headers are correctly propagated.

        This ensures that the auth context is request-scoped and not cached/shared.
        Internal entity calls always use service:evaluation as principal, but the
        on-behalf-of header should reflect the original requesting user.
        """
        access_log = _require_access_log(test_context)
        users = [
            "user-one@example.com",
            "user-two@example.com",
        ]

        for user in users:
            access_log.clear()

            response = test_context.test_client.get(
                "/apis/evaluation/v2/workspaces/default/metrics",
                headers={
                    "X-NMP-Principal-Id": user,
                    "X-NMP-Principal-Email": user,
                },
            )
            assert response.status_code == 200, f"User {user} got {response.status_code}: {response.text}"

            metric_requests = access_log.filter(path_contains="/entities/metric")
            for req in metric_requests:
                assert req.principal_id == "service:evaluation", (
                    f"Expected service:evaluation as principal in internal request to {req.path}, got {req.principal_id}"
                )
                assert req.on_behalf_of == user, (
                    f"Expected on-behalf-of {user} in internal request to {req.path}, got {req.on_behalf_of}"
                )

    @mock.patch("nmp.evaluator.app.inference.verify_model_reachable", new_callable=mock.AsyncMock)
    def test_job_creation_propagates_headers_to_jobs_service(
        self, mock_verify_model: mock.AsyncMock, test_context: ClientContext
    ):
        """Verify that job creation propagates user headers to jobs service.

        Uses a custom LLM judge metric (based on tests/data/metric-jobs/llm-judge-offline.json).
        Verifies that a POST to /apis/jobs/v2/workspaces/default/jobs is made with correct headers.
        """
        access_log = _require_access_log(test_context)
        # Mock model reachability check to pass (precheck will succeed)
        mock_verify_model.return_value = {"status": "ok"}
        access_log.clear()

        test_principal = "job-creator@example.com"

        # Job request using custom LLM judge metric.
        # Based on services/evaluator/tests/data/metric-jobs/llm-judge-offline.json
        # Wrapped in 'spec' envelope as required by the job route factory
        job_request = {
            "spec": {
                "dataset": {
                    "rows": [
                        {"input": "hi", "output": "hello world"},
                    ]
                },
                "metric": {
                    "type": "llm-judge",
                    "model": {
                        "name": "test-judge",
                        "url": "http://test-inference:8000/v1/chat/completions",
                    },
                    "scores": [
                        {
                            "name": "quality",
                            "rubric": [
                                {"label": "bad", "value": 0},
                                {"label": "good", "value": 1},
                            ],
                        }
                    ],
                },
            }
        }

        response = test_context.test_client.post(
            "/apis/evaluation/v2/workspaces/default/metric-jobs",
            json=job_request,
            headers={
                "X-NMP-Principal-Id": test_principal,
                "X-NMP-Principal-Email": test_principal,
            },
        )

        # Should not be 401/403 - auth passed
        assert response.status_code not in (
            401,
            403,
        ), f"Expected auth to pass, got {response.status_code}: {response.text}"

        # Verify a POST to /apis/jobs/v2/workspaces/default/jobs was made (internal job creation)
        internal_jobs_requests = access_log.filter(
            path_startswith="/apis/jobs/v2/workspaces/default/jobs",
            method="POST",
        )

        assert len(internal_jobs_requests) > 0, (
            f"Expected POST to /apis/jobs/v2/workspaces/default/jobs. "
            f"Captured POST requests: {[r.path for r in access_log.filter(method='POST')]}"
        )

        # Verify the jobs service call used the correct principal
        for req in internal_jobs_requests:
            assert req.principal_id == test_principal, (
                f"Expected principal {test_principal} in jobs request to {req.path}, got {req.principal_id}"
            )
