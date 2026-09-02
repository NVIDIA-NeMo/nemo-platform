# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""What `GET /session` on the orchestrator proxy is allowed to tell the sandboxed job."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sandboxed_gym.config import BrokerEndpoint
from sandboxed_gym.host.models import GymHostHandle
from sandboxed_gym.orchestrator import SandboxedGymSession
from sandboxed_gym.proxy_app import AUTH_HEADER, build_proxy_app
from sandboxed_gym.serve_config import SandboxedGymServeConfig


def _session(rollout_auth_token: str | None) -> SandboxedGymSession:
    cfg = SandboxedGymServeConfig.model_validate(
        {
            "job_id": "job-1",
            "sandbox": {
                "image": "runtime:dev",
                "network_policy": {"egress_allow": []},
                "environment_pvc_claim": "env",
                "workspace_pvc_claim": "work",
            },
            "rollout_auth_token": rollout_auth_token,
        }
    )
    return SandboxedGymSession(
        cfg=cfg,
        broker_server=MagicMock(),
        broker=BrokerEndpoint(url="http://broker.svc:1", host="broker.svc", port=1, token="btok"),
        host_provider=MagicMock(),
        host=GymHostHandle(
            host_id="h1",
            health_url="http://host/health",
            rollout_url="http://host/rollouts/run",
            headers={},
        ),
        orchestrator_url="http://orch.svc:8090",
    )


def test_an_unauthenticated_session_route_withholds_the_broker_token() -> None:
    """Without a rollout token the route is open to anything that can reach the proxy -- which
    includes the sandboxed job the broker credential is meant to keep on the far side of."""
    client = TestClient(build_proxy_app(_session(None)))

    body = client.get("/session").json()

    assert body["broker_url"] == "http://broker.svc:1"
    assert "broker_token" not in body
    assert "rollout_auth_token" not in body


def test_an_authenticated_caller_still_gets_the_broker_token() -> None:
    client = TestClient(build_proxy_app(_session("secret")))

    body = client.get("/session", headers={AUTH_HEADER: "secret"}).json()

    assert body["broker_token"] == "btok"
    assert body["rollout_auth_token"] == "secret"


def test_the_session_route_rejects_a_wrong_token() -> None:
    client = TestClient(build_proxy_app(_session("secret")))

    assert client.get("/session", headers={AUTH_HEADER: "nope"}).status_code == 401
