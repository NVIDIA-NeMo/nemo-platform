# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests that drive the typed ``JobsClient`` against the real Jobs
service routes (in-memory ASGI app).

Unlike ``tests/jobs/test_endpoints.py`` (which only asserts ``PreparedRequest``
shape) these exercise ``send()`` all the way through path resolution, HTTP,
and response parsing — the layer where response-type bugs actually surface.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from nemo_platform_plugin.jobs.client import AsyncJobsClient


@pytest.fixture
def jobs_client(test_client: AsyncClient) -> AsyncJobsClient:
    """A typed AsyncJobsClient bound to the in-memory Jobs app.

    Mirrors how ``test_sdk`` builds the Stainless SDK, but returns the new
    typed client so responses flow through ``NemoClient.send()``.
    """
    return AsyncJobsClient(base_url=str(test_client.base_url), http_client=test_client)


@pytest.mark.asyncio
async def test_get_execution_profiles_parses_response(jobs_client: AsyncJobsClient, test_client: AsyncClient):
    """Regression: ``get_execution_profiles`` must parse a successful response.

    The route returns a JSON *array* of profiles. ``send()`` parses the body
    with ``response_type.model_validate(...)``, so a bare ``list[...]`` return
    annotation raises ``AttributeError: type object 'list' has no attribute
    'model_validate'``. This test drives the real route through the typed
    client and fails until the endpoint uses a parseable response type.
    """
    # Sanity: the raw route really does return a JSON list (server side is fine).
    raw = await test_client.get("/apis/jobs/v2/execution-profiles")
    assert raw.status_code == 200
    assert isinstance(raw.json(), list)

    # The actual regression: the typed client must not crash parsing it.
    resp = await jobs_client.get_execution_profiles()
    profiles = resp.data()
    assert isinstance(profiles, list)


async def _create_hello_world_job(test_client: AsyncClient, name: str = "e2e-client-job") -> None:
    """Create a job via the hello-world factory route (service-specific body)."""
    resp = await test_client.post(
        "/apis/jobs/v2/workspaces/default/hello-world/jobs",
        json={
            "name": name,
            "description": "typed-client e2e",
            "spec": {"config": {"key": "Value"}, "target": "str"},
            "ownership": {"user": "u", "service": "s"},
        },
    )
    assert resp.status_code == 201, f"create failed: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_list_jobs_round_trips_through_client(jobs_client: AsyncJobsClient, test_client: AsyncClient):
    """``list_jobs`` must page + parse real ``PlatformJobResponse`` items."""
    await _create_hello_world_job(test_client, name="list-me")

    page = (await jobs_client.list_jobs(workspace="default")).page()
    assert page.total_results is not None and page.total_results >= 1
    names = [j.name for j in page.items]
    assert "list-me" in names
    # items are the plugin DTO, fully parsed
    job = next(j for j in page.items if j.name == "list-me")
    assert job.workspace == "default"
    assert job.status is not None


@pytest.mark.asyncio
async def test_get_job_and_status_round_trip(jobs_client: AsyncJobsClient, test_client: AsyncClient):
    """``get_job`` and ``get_job_status`` must parse their real responses."""
    await _create_hello_world_job(test_client, name="get-me")

    job = (await jobs_client.get_job(name="get-me", workspace="default")).data()
    assert job.name == "get-me"
    assert job.fileset  # non-empty

    status = (await jobs_client.get_job_status(name="get-me", workspace="default")).data()
    assert status.status is not None
