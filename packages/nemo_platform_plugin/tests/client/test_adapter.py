# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx
import pytest
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.types import RetryPolicy
from nemo_platform_plugin.jobs import endpoints
from nemo_platform_plugin.jobs.client import JobsClient
from nemo_platform_plugin.workspaces.client import AsyncWorkspacesClient, WorkspacesClient


class _Provider:
    def __init__(self, token: str) -> None:
        self._token = token

    def get_access_token(self) -> str:
        return self._token

    async def get_access_token_async(self) -> str:
        return self._token


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


def test_client_from_platform_falls_back_to_sdk_prepare_url() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    platform = NeMoPlatform(
        base_url="http://gateway",
        workspace="default",
        http_client=http_client,
    )

    def prepare_url(url: str) -> str:
        return url.replace("http://gateway/apis/jobs", "http://127.0.0.1:8080/apis/jobs")

    platform._prepare_url = prepare_url  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

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


def test_client_from_platform_propagates_timeout() -> None:
    """``platform.with_options(timeout=...)`` must reach the typed client.

    Both clients share one httpx client, whose own timeout ``with_options`` does
    not touch — so the typed client has to carry the override itself or long
    transfers silently run on the transport's original budget.
    """
    upload_timeout = httpx.Timeout(30.0, write=10 * 60, read=5 * 60)
    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        timeout=httpx.Timeout(60.0),
    )
    platform = NeMoPlatform(base_url="http://test", workspace="default", http_client=http_client)

    scoped = platform.with_options(timeout=upload_timeout)
    client = client_from_platform(scoped, JobsClient)

    assert client._timeout == upload_timeout
    # The shared transport is untouched, which is why the override is needed.
    assert scoped._client.timeout == httpx.Timeout(60.0)


def test_client_from_platform_carries_default_timeout() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        timeout=httpx.Timeout(60.0),
    )
    platform = NeMoPlatform(base_url="http://test", workspace="default", http_client=http_client)

    client = client_from_platform(platform, JobsClient)

    assert client._timeout == platform.timeout


def test_client_from_platform_carries_disabled_timeout() -> None:
    """``timeout=None`` means "no timeout", not "no override"."""
    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        timeout=httpx.Timeout(60.0),
    )
    platform = NeMoPlatform(base_url="http://test", workspace="default", http_client=http_client)

    client = client_from_platform(platform.with_options(timeout=None), JobsClient)

    # Not the transport's 60s: httpx reads an all-None Timeout as "wait forever".
    assert client._timeout == httpx.Timeout(None)


def test_client_from_platform_preserves_token_provider_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "workspace-id",
                "name": "default",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    platform = NeMoPlatform(
        base_url="http://test",
        workspace="default",
        default_headers={"X-NMP-Internal": "true"},
        http_client=http_client,
        token_provider=_Provider("adapter-token"),
    )

    client = client_from_platform(platform, WorkspacesClient)
    workspace = client.get_workspace(name="default").data()

    assert workspace.name == "default"
    assert requests[0].headers["Authorization"] == "Bearer adapter-token"
    assert requests[0].headers["X-NMP-Internal"] == "true"
    assert "X-NMP-Principal-Id" not in requests[0].headers


@pytest.mark.asyncio
async def test_async_client_from_platform_preserves_token_provider_auth() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "workspace-id",
                "name": "default",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    platform = AsyncNeMoPlatform(
        base_url="http://test",
        workspace="default",
        default_headers={"X-NMP-Internal": "true"},
        http_client=http_client,
        token_provider=_Provider("async-adapter-token"),
    )

    try:
        client = client_from_platform(platform, AsyncWorkspacesClient)
        workspace = (await client.get_workspace(name="default")).data()

        assert workspace.name == "default"
        assert requests[0].headers["Authorization"] == "Bearer async-adapter-token"
        assert requests[0].headers["X-NMP-Internal"] == "true"
        assert "X-NMP-Principal-Id" not in requests[0].headers
    finally:
        await http_client.aclose()
