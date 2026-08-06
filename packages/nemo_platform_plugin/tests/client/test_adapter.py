# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.types import RetryPolicy
from nemo_platform_plugin.jobs import endpoints
from nemo_platform_plugin.jobs.client import JobsClient


def test_client_from_platform_preserves_stainless_retry_policy() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    platform = NeMoPlatform(
        base_url="http://test",
        workspace="default",
        max_retries=4,
        http_client=http_client,
    )

    client = client_from_platform(platform, JobsClient)

    assert client.retry is not None
    assert client.retry == RetryPolicy(
        max_retries=4,
        retryable_status_codes=(408, 409, 429),
        retry_all_server_errors=True,
        respect_retry_decision_headers=True,
        respect_retry_after_headers=True,
    )


def test_client_from_platform_prefers_platform_request_router() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    platform = NeMoPlatform(
        base_url="http://gateway",
        workspace="default",
        http_client=http_client,
    )

    class RequestRouter:
        def resolve(self, url: str) -> str:
            return url.replace("http://gateway/apis/jobs", "http://127.0.0.1:8080/apis/jobs")

    platform._nmp_request_router = RequestRouter()  # type: ignore[attr-defined]

    client = client_from_platform(platform, JobsClient)

    request = endpoints.list_steps(workspace="default", name="job-1")
    assert client._resolve_path(request) == ("http://127.0.0.1:8080/apis/jobs/v2/workspaces/default/jobs/job-1/steps")


def test_client_from_platform_falls_back_to_sdk_prepare_url() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    platform = NeMoPlatform(
        base_url="http://gateway",
        workspace="default",
        http_client=http_client,
    )

    def prepare_url(url: str) -> str:
        return url.replace("http://gateway/apis/jobs", "http://127.0.0.1:8080/apis/jobs")

    platform._prepare_url = prepare_url  # type: ignore[method-assign]

    client = client_from_platform(platform, JobsClient)

    request = endpoints.list_steps(workspace="default", name="job-1")
    assert client._resolve_path(request) == ("http://127.0.0.1:8080/apis/jobs/v2/workspaces/default/jobs/job-1/steps")


def test_from_client_preserves_url_resolver() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    client = JobsClient(
        base_url="http://gateway",
        workspace="default",
        http_client=http_client,
        url_resolver=lambda url: url.replace("http://gateway/apis/jobs", "http://127.0.0.1:8080/apis/jobs"),
    )

    clone = JobsClient.from_client(client)

    request = endpoints.list_steps(workspace="default", name="job-1")
    assert clone._resolve_path(request) == ("http://127.0.0.1:8080/apis/jobs/v2/workspaces/default/jobs/job-1/steps")
