# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

import httpx
import pytest
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.jobs.sdk import AsyncJobsResource, JobsResource, jobs_sdk_resources
from nemo_platform_plugin.sdk import NemoPluginSDKResources

BASE = "http://test:8000"


def _platform_spec() -> dict[str, object]:
    return {"steps": [{"name": "step-one", "executor": {"provider": "cpu", "container": {"image": "x"}}}]}


def _job_payload(name: str = "my-job", status: str = "created") -> dict[str, object]:
    return {
        "id": f"{name}-id",
        "attempt_id": f"{name}-attempt",
        "name": name,
        "workspace": "default",
        "source": "test",
        "spec": {},
        "platform_spec": _platform_spec(),
        "fileset": "fs-1",
        "status": status,
    }


def _job_status_payload(status: str = "active") -> dict[str, object]:
    return {
        "id": "my-job-id",
        "name": "my-job",
        "status": status,
        "status_details": {},
        "error_details": None,
        "steps": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:01:00Z",
    }


def _step_payload(name: str = "step-one") -> dict[str, object]:
    return {
        "id": f"{name}-id",
        "entity_id": f"{name}-entity",
        "parent": "my-job-attempt",
        "attempt_id": "my-job-attempt",
        "name": name,
        "workspace": "default",
        "config": {},
        "status": "completed",
    }


def _step_with_context_payload(name: str = "step-one") -> dict[str, object]:
    return {
        "id": f"{name}-id",
        "job": "my-job",
        "attempt_id": "my-job-attempt",
        "fileset": "fs-1",
        "workspace": "default",
        "name": name,
        "status": "completed",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:01:00Z",
    }


def _task_payload(name: str = "task-one") -> dict[str, object]:
    return {
        "id": f"{name}-id",
        "entity_id": f"{name}-entity",
        "parent": "step-one-id",
        "step_id": "step-one-id",
        "name": name,
        "workspace": "default",
        "status": "completed",
        "status_details": {},
        "error_details": None,
        "error_stack": None,
    }


def _pagination_payload(page: int, total_pages: int) -> dict[str, int]:
    return {
        "page": page,
        "page_size": 1,
        "current_page_size": 1,
        "total_pages": total_pages,
        "total_results": total_pages,
    }


def test_jobs_sdk_resources_entry_point_shape() -> None:
    assert isinstance(jobs_sdk_resources, NemoPluginSDKResources)
    assert jobs_sdk_resources.sync_resource is JobsResource
    assert jobs_sdk_resources.async_resource is AsyncJobsResource


def test_platform_client_exposes_legacy_jobs_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, request=request, json=_job_status_payload(status="completed"))

    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_sdk",
        lambda: {"jobs": jobs_sdk_resources},
    )
    client = NeMoPlatform(
        base_url=BASE,
        workspace="default",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    status = client.jobs.get_status(name="my-job")

    assert status.status == "completed"
    assert seen[0].url.path == "/apis/jobs/v2/workspaces/default/jobs/my-job/status"


def test_jobs_resource_list_paginates_and_preserves_query_options() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [_job_payload(name=f"job-{page}")],
                "pagination": _pagination_payload(page=page, total_pages=2),
            },
        )

    platform = NeMoPlatform(
        base_url=BASE,
        workspace="default",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    resource = JobsResource(platform)

    first_page = resource.list(filter={"source": "test"}, page_size=1, sort="-created_at")
    all_jobs = list(first_page)

    assert first_page.data[0].name == "job-1"
    assert first_page.pagination is not None
    assert first_page.pagination.total_pages == 2
    assert first_page.has_next_page()
    assert first_page.next_page_info() is not None
    assert [job.name for job in all_jobs] == ["job-1", "job-2"]
    assert [request.url.params.get("page", "1") for request in seen] == ["1", "2"]
    assert json.loads(seen[0].url.params["filter"]) == {"source": "test"}
    assert seen[0].url.params["page_size"] == "1"
    assert seen[0].url.params["sort"] == "-created_at"


def test_jobs_resource_preserves_lifecycle_and_subresource_paths() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/steps/step-one/status"):
            return httpx.Response(200, request=request, json=_step_payload())
        if path.endswith("/status"):
            return httpx.Response(200, request=request, json=_job_status_payload(status="active"))
        if path.endswith("/cancel"):
            return httpx.Response(200, request=request, json=_job_payload(status="cancelled"))
        if path.endswith("/steps/step-one"):
            return httpx.Response(200, request=request, json=_step_payload())
        if path.endswith("/steps/step-one/tasks/task-one"):
            return httpx.Response(200, request=request, json=_task_payload())
        if path.endswith("/results/result-one"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "name": "result-one",
                    "job": "my-job",
                    "workspace": "default",
                    "artifact_url": "fileset://fs-1/result.json",
                    "artifact_storage_type": "fileset",
                },
            )
        if path.endswith("/logs"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": [
                        {
                            "timestamp": "2026-01-01T00:00:00Z",
                            "job": "my-job",
                            "job_step": "step-one",
                            "job_task": "task-one",
                            "message": "hello",
                        }
                    ],
                    "total": 1,
                    "next_page": None,
                    "prev_page": None,
                },
            )
        return httpx.Response(200, request=request, json=_job_payload())

    platform = NeMoPlatform(
        base_url=BASE,
        workspace="default",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    resource = JobsResource(platform)

    created = resource.create(platform_spec=_platform_spec(), source="test", spec={}, name="my-job")
    status = resource.get_status("my-job")
    cancelled = resource.cancel("my-job")
    step = resource.steps.retrieve("step-one", job="my-job")
    updated_step = resource.steps.update_status("step-one", job="my-job", status="completed")
    task = resource.tasks.create_or_update("task-one", job="my-job", step="step-one", status="completed")
    result = resource.results.create(
        "result-one",
        job="my-job",
        artifact_url="fileset://fs-1/result.json",
        artifact_storage_type="fileset",
    )
    logs = resource.get_logs("my-job", limit=10)

    assert created.name == "my-job"
    assert status.status == "active"
    assert cancelled.status == "cancelled"
    assert step.name == "step-one"
    assert updated_step.status == "completed"
    assert task.name == "task-one"
    assert result.name == "result-one"
    assert logs.data[0].message == "hello"
    assert [request.url.path for request in seen] == [
        "/apis/jobs/v2/workspaces/default/jobs",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/status",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/cancel",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/steps/step-one",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/steps/step-one/status",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/steps/step-one/tasks/task-one",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/results/result-one",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/logs",
    ]


@pytest.mark.asyncio
async def test_async_jobs_resource_can_be_awaited_or_iterated() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, request=request, json=_job_status_payload(status="completed"))
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [_job_payload(name=f"job-{page}")],
                "pagination": _pagination_payload(page=page, total_pages=2),
            },
        )

    platform = AsyncNeMoPlatform(
        base_url=BASE,
        workspace="default",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    resource = AsyncJobsResource(platform)

    try:
        first_page = await resource.list(filter={"source": "test"}, page_size=1)
        status = await resource.get_status("my-job")
        job_names: list[str] = []
        async for job in resource.list(filter={"source": "test"}, page_size=1):
            job_names.append(job.name)
    finally:
        await platform.close()

    assert first_page.data[0].name == "job-1"
    assert status.status == "completed"
    assert job_names == ["job-1", "job-2"]
    assert [request.url.path for request in seen] == [
        "/apis/jobs/v2/workspaces/default/jobs",
        "/apis/jobs/v2/workspaces/default/jobs/my-job/status",
        "/apis/jobs/v2/workspaces/default/jobs",
        "/apis/jobs/v2/workspaces/default/jobs",
    ]
    assert seen[3].url.params["page"] == "2"
