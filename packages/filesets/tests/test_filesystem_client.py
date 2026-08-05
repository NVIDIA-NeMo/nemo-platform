# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Client construction inside FilesetFileSystem.

Uploads and downloads run on the async client built by ``_ensure_async``, not on
the sync client the caller configured. Anything that client fails to carry over
is silently dropped from every transfer.
"""

from __future__ import annotations

import httpx
from filesets.filesystem.filesystem import FilesetFileSystem
from nemo_platform_plugin.client.types import RetryPolicy
from nemo_platform_plugin.files.client import FilesClient

BASE = "http://test:8000"
UPLOAD_TIMEOUT = httpx.Timeout(30.0, write=10 * 60, read=5 * 60)


def _sync_client(*, timeout: httpx.Timeout) -> FilesClient:
    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        timeout=timeout,
    )
    return FilesClient(
        base_url=BASE,
        workspace="default",
        http_client=http_client,
        retry=RetryPolicy(max_retries=2),
    )


def test_ensure_async_carries_transport_timeout() -> None:
    """Without this the new AsyncClient falls back to httpx's 5s default."""
    async_client = FilesetFileSystem._ensure_async(_sync_client(timeout=httpx.Timeout(60.0)))

    assert async_client._http.timeout == httpx.Timeout(60.0)
    assert async_client._http.timeout != httpx.Timeout(5.0)


def test_ensure_async_prefers_per_request_timeout_override() -> None:
    client = _sync_client(timeout=httpx.Timeout(60.0)).with_options(timeout=UPLOAD_TIMEOUT)

    async_client = FilesetFileSystem._ensure_async(client)

    assert async_client._http.timeout == UPLOAD_TIMEOUT
    assert async_client._timeout == UPLOAD_TIMEOUT


def test_ensure_async_preserves_workspace_and_retry() -> None:
    client = _sync_client(timeout=httpx.Timeout(60.0))

    async_client = FilesetFileSystem._ensure_async(client)

    assert async_client.workspace == "default"
    assert async_client.retry == RetryPolicy(max_retries=2)


def test_upload_timeout_survives_the_whole_client_chain() -> None:
    """End to end: an SDK-level timeout override reaches the streaming transport."""
    from nemo_platform import NeMoPlatform

    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        timeout=httpx.Timeout(60.0),
    )
    platform = NeMoPlatform(base_url=BASE, workspace="default", http_client=http_client)

    fs = platform.with_options(timeout=UPLOAD_TIMEOUT).files.fsspec

    assert fs._client._http.timeout == UPLOAD_TIMEOUT
