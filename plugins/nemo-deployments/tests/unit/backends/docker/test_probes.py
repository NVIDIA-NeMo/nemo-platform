# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Docker readiness probes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from nemo_deployments_plugin.backends.docker.probes import check_readiness_probe
from nemo_deployments_plugin.entities import HTTPGetAction, Probe, TCPSocketAction


@pytest.mark.asyncio
async def test_http_probe_without_host_url_not_ready() -> None:
    container = MagicMock()
    probe = Probe(http_get=HTTPGetAction(path="/health", port=8080))

    ready, reason = await check_readiness_probe(
        container=container,
        probe=probe,
        host_url=None,
    )

    assert ready is False
    assert "no host_url available" in reason


@pytest.mark.asyncio
async def test_tcp_probe_without_host_url_not_ready() -> None:
    container = MagicMock()
    probe = Probe(tcp_socket=TCPSocketAction(port=8080))

    ready, reason = await check_readiness_probe(
        container=container,
        probe=probe,
        host_url=None,
    )

    assert ready is False
    assert "no host_url available" in reason
