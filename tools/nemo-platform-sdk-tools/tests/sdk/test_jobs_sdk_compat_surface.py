# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import httpx
import pytest
import respx
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform._response import AsyncStreamedBinaryAPIResponse, BinaryAPIResponse, StreamedBinaryAPIResponse
from nemo_platform.types.jobs import PlatformJobStep, PlatformJobTask
from nemo_platform.types.shared import PlatformJobStatusResponse

BASE_URL = "http://nemo.test"


def _status_payload(status: str = "completed") -> dict[str, object]:
    return {
        "id": "job-id",
        "created_at": "2026-01-01T00:00:00Z",
        "error_details": {},
        "name": "customizer-job",
        "status": status,
        "status_details": {},
        "steps": [],
        "updated_at": "2026-01-01T00:01:00Z",
    }


def _step_payload(name: str = "training") -> dict[str, object]:
    return {
        "id": f"{name}-id",
        "attempt_id": "attempt-1",
        "created_at": "2026-01-01T00:00:00Z",
        "db_version": 1,
        "entity_id": f"{name}-id",
        "name": name,
        "parent": "attempt-1",
        "status": "active",
        "updated_at": "2026-01-01T00:01:00Z",
        "workspace": "default",
    }


def _task_payload(name: str = "worker-0") -> dict[str, object]:
    return {
        "id": f"{name}-id",
        "created_at": "2026-01-01T00:00:00Z",
        "db_version": 1,
        "entity_id": f"{name}-id",
        "name": name,
        "parent": "training-id",
        "status": "completed",
        "step_id": "training-id",
        "updated_at": "2026-01-01T00:01:00Z",
        "workspace": "default",
    }


def test_jobs_sdk_compat_exposes_customizer_doc_surface() -> None:
    client = NeMoPlatform(base_url=BASE_URL, workspace="default")

    assert callable(client.jobs.cancel)
    assert callable(client.jobs.list)
    assert callable(client.jobs.results.download)
    assert callable(client.jobs.tasks.retrieve)
    assert callable(client.jobs.steps.retrieve)
    assert callable(client.jobs.with_raw_response.get_status)
    assert callable(client.jobs.with_streaming_response.results.download)
    assert callable(client.with_raw_response.jobs.get_status)
    assert callable(client.with_streaming_response.jobs.results.download)
    assert PlatformJobStep.__name__ == "PlatformJobStep"
    assert PlatformJobTask.__name__ == "PlatformJobTask"
    assert PlatformJobStatusResponse.__name__ == "PlatformJobStatusResponse"


@respx.mock
def test_jobs_sdk_compat_status_call_uses_legacy_resource_path() -> None:
    route = respx.get(f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/status").mock(
        return_value=httpx.Response(200, json=_status_payload())
    )

    client = NeMoPlatform(base_url=BASE_URL, workspace="default")
    response = client.jobs.get_status("customizer-job")

    assert route.called
    assert isinstance(response, PlatformJobStatusResponse)
    assert response.name == "customizer-job"
    assert response.status == "completed"


@respx.mock
def test_jobs_sdk_compat_subresources_use_legacy_paths() -> None:
    step_route = respx.get(f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/steps/training").mock(
        return_value=httpx.Response(200, json=_step_payload("training"))
    )
    task_route = respx.get(
        f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/steps/training/tasks/worker-0"
    ).mock(return_value=httpx.Response(200, json=_task_payload("worker-0")))
    task_list_route = respx.get(
        f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/steps/training/tasks"
    ).mock(return_value=httpx.Response(200, json={"data": [_task_payload("worker-0")]}))

    client = NeMoPlatform(base_url=BASE_URL, workspace="default")
    step = client.jobs.steps.retrieve("training", job="customizer-job")
    task = client.jobs.tasks.retrieve("worker-0", job="customizer-job", step="training")
    task_list = client.jobs.tasks.list("training", job="customizer-job")

    assert step_route.called
    assert task_route.called
    assert task_list_route.called
    assert isinstance(step, PlatformJobStep)
    assert step.name == "training"
    assert isinstance(task, PlatformJobTask)
    assert task.name == "worker-0"
    assert task_list.data[0].name == "worker-0"


@respx.mock
def test_jobs_sdk_compat_result_download_uses_binary_response_and_legacy_path() -> None:
    route = respx.get(f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/results/metrics/download").mock(
        return_value=httpx.Response(200, content=b"metric-bytes")
    )

    client = NeMoPlatform(base_url=BASE_URL, workspace="default")
    response = client.jobs.results.download("metrics", job="customizer-job")

    assert route.called
    assert response.read() == b"metric-bytes"
    assert response.is_closed is True
    assert isinstance(response, BinaryAPIResponse)


@respx.mock
def test_jobs_sdk_compat_top_level_raw_and_streaming_wrappers_use_legacy_paths() -> None:
    raw_route = respx.get(f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/status").mock(
        return_value=httpx.Response(200, json=_status_payload("active"))
    )
    streaming_route = respx.get(
        f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/results/metrics/download"
    ).mock(return_value=httpx.Response(200, content=b"streamed-metrics"))

    client = NeMoPlatform(base_url=BASE_URL, workspace="default")
    raw_response = client.with_raw_response.jobs.get_status("customizer-job")
    parsed_status = raw_response.parse()
    with client.with_streaming_response.jobs.results.download("metrics", job="customizer-job") as streaming_response:
        assert streaming_response.read() == b"streamed-metrics"
        assert isinstance(streaming_response, StreamedBinaryAPIResponse)

    assert raw_route.called
    assert streaming_route.called
    assert raw_response.status_code == 200
    assert parsed_status.status == "active"
    assert streaming_response.is_closed is True


@respx.mock
@pytest.mark.asyncio
async def test_async_jobs_sdk_compat_top_level_raw_and_streaming_wrappers_use_legacy_paths() -> None:
    raw_route = respx.get(f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/status").mock(
        return_value=httpx.Response(200, json=_status_payload("active"))
    )
    streaming_route = respx.get(
        f"{BASE_URL}/apis/jobs/v2/workspaces/default/jobs/customizer-job/results/metrics/download"
    ).mock(return_value=httpx.Response(200, content=b"async-streamed-metrics"))

    async with AsyncNeMoPlatform(base_url=BASE_URL, workspace="default") as client:
        raw_response = await client.with_raw_response.jobs.get_status("customizer-job")
        parsed_status = await raw_response.parse()
        async with client.with_streaming_response.jobs.results.download(
            "metrics", job="customizer-job"
        ) as streaming_response:
            assert await streaming_response.read() == b"async-streamed-metrics"
            assert isinstance(streaming_response, AsyncStreamedBinaryAPIResponse)

    assert raw_route.called
    assert streaming_route.called
    assert raw_response.status_code == 200
    assert parsed_status.status == "active"
    assert streaming_response.is_closed is True
