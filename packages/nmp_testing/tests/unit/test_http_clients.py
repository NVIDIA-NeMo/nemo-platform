# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import httpx
import pytest
from nmp.common.config import PlatformConfig
from nmp.common.platform_endpoint import resolve_platform_endpoint
from nmp.testing.http_clients import routed_async_mock_client, routed_mock_client


@pytest.fixture
def service_endpoint():
    config = PlatformConfig(  # type: ignore[abstract]
        base_url="http://platform:8080",
        service_discovery={"entities": "http://entities:9090/entities-prefix"},
    )
    return resolve_platform_endpoint(config)


def test_routed_mock_client_applies_platform_endpoint_routes(service_endpoint):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    with routed_mock_client(handler, endpoint=service_endpoint) as client:
        client.get("http://platform:8080/apis/entities/v2/workspaces?limit=5")

    assert str(captured[0].url) == "http://entities:9090/entities-prefix/apis/entities/v2/workspaces?limit=5"
    assert captured[0].headers["host"] == "entities:9090"


async def test_routed_async_mock_client_applies_platform_endpoint_routes(service_endpoint):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    async with routed_async_mock_client(handler, endpoint=service_endpoint) as client:
        await client.get("http://platform:8080/apis/entities/v2/workspaces?limit=5")

    assert str(captured[0].url) == "http://entities:9090/entities-prefix/apis/entities/v2/workspaces?limit=5"
    assert captured[0].headers["host"] == "entities:9090"
