# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for cross-job session handoff and broker advertise_url."""

from __future__ import annotations

from unittest.mock import MagicMock

from sandboxed_gym.broker import EpisodeBrokerServer
from sandboxed_gym.config import BrokerEndpoint, EpisodeBrokerConfig
from sandboxed_gym.host.models import GymHostHandle
from sandboxed_gym.orchestrator import SandboxedGymSession
from sandboxed_gym.serve_config import SandboxedGymServeConfig


def test_advertise_url_preferred_over_host():
    cfg = EpisodeBrokerConfig(
        job_id="job-1",
        backend="memory",
        allow_insecure_memory_backend=True,
        host="10.0.0.9",
        advertise_url="http://broker.job-1.svc:8741",
        port=8741,
    )
    server = EpisodeBrokerServer(cfg)
    url, host, port = server._resolve_advertise(8741)
    assert url == "http://broker.job-1.svc:8741"
    assert host == "broker.job-1.svc"
    assert port == 8741


def test_advertise_url_keeps_its_path_when_the_port_is_implied():
    """The bind port has to be spliced in ahead of the path, not in place of it: the Gym host
    treats this URL as a base and appends its own routes to it."""
    cfg = EpisodeBrokerConfig(
        job_id="job-1",
        backend="memory",
        allow_insecure_memory_backend=True,
        advertise_url="http://ingress.svc/broker/job-1",
    )
    url, host, port = EpisodeBrokerServer(cfg)._resolve_advertise(8741)
    assert url == "http://ingress.svc:8741/broker/job-1"
    assert (host, port) == ("ingress.svc", 8741)


def test_session_descriptor_orchestrator_mode():
    cfg = SandboxedGymServeConfig.model_validate(
        {
            "job_id": "job-1",
            "sandbox": {
                "image": "runtime:dev",
                "network_policy": {"egress_allow": []},
                "environment_pvc_claim": "env",
                "workspace_pvc_claim": "work",
            },
            "rollout_auth_token": "secret",
        }
    )
    broker = BrokerEndpoint(url="http://broker.svc:1", host="broker.svc", port=1, token="btok")
    host = GymHostHandle(
        host_id="h1",
        health_url="http://host/health",
        rollout_url="http://host/rollouts/run",
        headers={},
    )
    session = SandboxedGymSession(
        cfg=cfg,
        broker_server=MagicMock(),
        broker=broker,
        host_provider=MagicMock(),
        host=host,
        orchestrator_url="http://orch.svc:8090",
    )
    desc = session.descriptor(mode="orchestrator")
    assert desc.orchestrator_url == "http://orch.svc:8090"
    assert desc.rollout_url == "http://orch.svc:8090/rollouts/run"
    assert desc.broker_token == "btok"
    assert desc.rollout_auth_token == "secret"
    assert desc.health_url == "http://host/health"
