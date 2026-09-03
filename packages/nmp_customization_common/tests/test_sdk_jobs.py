# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx
import pytest
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.jobs.schemas import PlatformJobStatusResponse
from nmp.customization_common.sdk.client import AsyncJobsResource, JobsResource

BASE = "http://test:8000"


class AutomodelJobsResource(JobsResource):
    backend = "automodel"


class AsyncAutomodelJobsResource(AsyncJobsResource):
    backend = "automodel"


def _job_payload(name: str = "customizer-job", status: str = "active") -> dict[str, object]:
    return {
        "id": f"job-{name}",
        "attempt_id": f"attempt-{name}",
        "name": name,
        "workspace": "default",
        "source": "automodel",
        "spec": {},
        "platform_spec": {},
        "fileset": f"fileset-{name}",
        "status": status,
        "status_details": {},
        "error_details": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:01:00Z",
    }


def _status_payload(name: str = "customizer-job", status: str = "active") -> dict[str, object]:
    return {
        "id": f"job-{name}",
        "name": name,
        "status": status,
        "status_details": {},
        "error_details": None,
        "steps": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:01:00Z",
    }


def test_get_job_resource_fetches_status_from_customizer_route() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, request=request, json=_status_payload(status="completed"))
        return httpx.Response(200, request=request, json=_job_payload())

    platform = NeMoPlatform(
        base_url=BASE,
        workspace="default",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    status = AutomodelJobsResource(platform).get_job_resource("customizer-job").get_status()

    assert isinstance(status, PlatformJobStatusResponse)
    assert status.name == "customizer-job"
    assert status.status == "completed"
    assert [request.url.path for request in seen] == [
        "/apis/customization/v2/workspaces/default/automodel/jobs/customizer-job",
        "/apis/customization/v2/workspaces/default/automodel/jobs/customizer-job/status",
    ]


@pytest.mark.asyncio
async def test_async_get_job_resource_fetches_status_from_customizer_route() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, request=request, json=_status_payload(status="completed"))
        return httpx.Response(200, request=request, json=_job_payload())

    platform = AsyncNeMoPlatform(
        base_url=BASE,
        workspace="default",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    jobs = AsyncAutomodelJobsResource(platform)

    resource = await jobs.get_job_resource("customizer-job", workspace="default")
    status = await resource.get_status()

    assert status.status == "completed"
    assert [request.url.path for request in seen] == [
        "/apis/customization/v2/workspaces/default/automodel/jobs/customizer-job",
        "/apis/customization/v2/workspaces/default/automodel/jobs/customizer-job/status",
    ]
