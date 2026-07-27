# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the service-principal auth-proxy sidecar forwarder."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import respx
from fastapi.testclient import TestClient
from nmp.common.auth.workload_proxy.main import build_app


@respx.mock
def test_forward_stamps_service_principal_and_preserves_path() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.post(f"{upstream}/apis/inference-gateway/v2/workspaces/default/openai/-/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    app = build_app(base_url=upstream, principal="agents")
    client = TestClient(app)

    resp = client.post(
        "/apis/inference-gateway/v2/workspaces/default/openai/-/v1/chat/completions",
        json={"model": "m", "messages": []},
        headers={"authorization": "Bearer not-used"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert route.called
    sent = route.calls.last.request
    # The proxy sets the service-principal identity and drops the placeholder auth.
    assert sent.headers["x-nmp-principal-id"] == "service:agents"
    assert "authorization" not in {k.lower() for k in sent.headers}


@respx.mock
def test_forward_normalizes_bare_principal_name() -> None:
    upstream = "http://nemo-platform-api:8080"
    route = respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(200, json={}))
    # Already-prefixed principal is passed through unchanged.
    app = build_app(base_url=upstream, principal="service:models")
    client = TestClient(app)
    client.get("/apis/entities/v2/workspaces")
    assert route.calls.last.request.headers["x-nmp-principal-id"] == "service:models"


@respx.mock
def test_forward_passes_through_upstream_status() -> None:
    upstream = "http://nemo-platform-api:8080"
    respx.get(f"{upstream}/apis/entities/v2/workspaces").mock(return_value=httpx.Response(403, json={"detail": "no"}))
    app = build_app(base_url=upstream, principal="agents")
    client = TestClient(app)

    resp = client.get("/apis/entities/v2/workspaces")
    assert resp.status_code == 403


def test_healthz_does_not_require_upstream() -> None:
    app = build_app(base_url="http://nemo-platform-api:8080", principal="agents")
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_lifespan_closes_upstream_client() -> None:
    # Entering TestClient as a context manager runs the lifespan; the shared
    # httpx client's connection pool must be closed on shutdown.
    created: list[httpx.AsyncClient] = []
    real_async_client = httpx.AsyncClient

    def _tracking_client(*args, **kwargs) -> httpx.AsyncClient:
        client = real_async_client(*args, **kwargs)
        created.append(client)
        return client

    with patch("nmp.common.auth.workload_proxy.main.httpx.AsyncClient", side_effect=_tracking_client):
        app = build_app(base_url="http://nemo-platform-api:8080", principal="agents")

    assert len(created) == 1
    upstream_client = created[0]
    with TestClient(app) as test_client:
        assert test_client.get("/healthz").status_code == 200
        assert upstream_client.is_closed is False
    assert upstream_client.is_closed is True
