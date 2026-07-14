# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.jobs.client import JobsClient


def test_client_from_platform_preserves_retry_count_with_nemoclient_defaults() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    platform = NeMoPlatform(
        base_url="http://test",
        workspace="default",
        max_retries=4,
        http_client=http_client,
    )

    client = client_from_platform(platform, JobsClient)

    assert client.retry is not None
    assert client.retry.max_retries == 4
    assert client.retry.retryable_status_codes == (502, 503, 504, 429)
