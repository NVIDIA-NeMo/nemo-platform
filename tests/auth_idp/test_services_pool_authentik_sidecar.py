# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from e2e.services_pool import RunningServices, RunningSidecar, _start_config_sidecars, _stop_sidecar_handles
from tests.auth_idp.providers import ProviderConfig
from tests.auth_idp.sidecars import start_authentik_sidecar

pytestmark = [pytest.mark.auth_idp]


def test_start_config_sidecars_passes_live_services_url_to_authentik(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, str, str, Path]] = []
    closed: list[bool] = []

    def fake_start_authentik_sidecar(sidecar_config, services, config_hash, runtime_root):
        calls.append((sidecar_config["provider"], services.url, config_hash, runtime_root))
        return RunningSidecar(
            name="authentik",
            metadata={"discovery_url": "http://127.0.0.1:19000/application/o/nemo/.well-known/openid-configuration"},
            close=lambda: closed.append(True),
        )

    monkeypatch.setattr("e2e.services_pool.start_authentik_sidecar", fake_start_authentik_sidecar)
    services = RunningServices(
        url="http://127.0.0.1:8081",
        log_path=None,
        proc=None,
        config_path=None,
    )

    metadata, handles = _start_config_sidecars(
        config_data={"e2e_sidecars": {"authentik": {"provider": "authentik"}}},
        services=services,
        config_hash="abc123",
        runtime_root=tmp_path,
    )

    assert calls == [("authentik", "http://127.0.0.1:8081", "abc123", tmp_path)]
    assert metadata["authentik"]["discovery_url"].endswith("/.well-known/openid-configuration")
    assert len(handles) == 1


def test_start_authentik_sidecar_requires_docker_backed_services_metadata(tmp_path: Path):
    with pytest.raises(pytest.UsageError, match="authentik e2e sidecar requires Docker-backed services metadata"):
        start_authentik_sidecar(
            {"provider": "authentik"},
            services=RunningServices(url="http://127.0.0.1:8081", log_path=None, proc=None, config_path=None),
            config_hash="abc123",
            runtime_root=tmp_path,
        )


def test_stop_sidecar_handles_closes_in_reverse_order():
    events: list[str] = []
    first = RunningSidecar(name="first", metadata={}, close=lambda: events.append("first"))
    second = RunningSidecar(name="second", metadata={}, close=lambda: events.append("second"))

    _stop_sidecar_handles([first, second])

    assert events == ["second", "first"]


def test_start_authentik_sidecar_uses_docker_assigned_host_ports(monkeypatch, tmp_path: Path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    initial_runtime = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=compose_file,
        gateway_base_url="http://127.0.0.1:0",
        issuer_url="http://127.0.0.1:0/application/o/nemo/",
        discovery_url="http://127.0.0.1:0/application/o/nemo/.well-known/openid-configuration",
        nemo_config=tmp_path / "nemo-auth.yaml",
        machine_principal_id="svc-nemo-ci",
        machine_expected_groups=["nemo-editors"],
        token_endpoint="http://127.0.0.1:0/application/o/token/",
        human_grant={"grant_type": "password"},
        machine_grant={"grant_type": "client_credentials"},
        healthchecks=[{"kind": "http", "url": "http://127.0.0.1:0/health"}],
        startup_timeouts={
            "healthchecks_seconds": 600,
            "gateway_seconds": 30,
            "token_endpoint_seconds": 180,
        },
        compose_project_name="authentik-e2e-abc123",
    )
    finalized_runtime = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=compose_file,
        gateway_base_url="http://127.0.0.1:38123",
        issuer_url="http://127.0.0.1:39123/application/o/nemo/",
        discovery_url="http://127.0.0.1:39123/application/o/nemo/.well-known/openid-configuration",
        nemo_config=tmp_path / "nemo-auth.yaml",
        machine_principal_id="svc-nemo-ci",
        machine_expected_groups=["nemo-editors"],
        token_endpoint="http://127.0.0.1:39123/application/o/token/",
        human_grant={"grant_type": "password"},
        machine_grant={"grant_type": "client_credentials"},
        healthchecks=[{"kind": "http", "url": "http://127.0.0.1:39123/health"}],
        startup_timeouts={
            "healthchecks_seconds": 600,
            "gateway_seconds": 30,
            "token_endpoint_seconds": 180,
        },
        compose_project_name="authentik-e2e-abc123",
    )
    port_calls: list[tuple[str, int, str | None, dict[str, str] | None]] = []
    up_calls: list[dict[str, str] | None] = []
    down_calls: list[dict[str, str] | None] = []

    def fake_compose_published_port(compose_file, service, container_port, *, project_name=None, env=None):
        port_calls.append((service, container_port, project_name, env))
        return {"gateway": 38123, "authentik-server": 39123}[service]

    monkeypatch.setattr("tests.auth_idp.sidecars.render_authentik_runtime_bundle", lambda **kwargs: initial_runtime)
    monkeypatch.setattr("tests.auth_idp.sidecars.configure_authentik_gateway_upstream", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "tests.auth_idp.sidecars.compose_down", lambda *args, **kwargs: down_calls.append(kwargs.get("env"))
    )
    monkeypatch.setattr(
        "tests.auth_idp.sidecars.compose_up", lambda *args, **kwargs: up_calls.append(kwargs.get("env"))
    )
    monkeypatch.setattr("tests.auth_idp.sidecars.compose_published_port", fake_compose_published_port)
    monkeypatch.setattr(
        "tests.auth_idp.sidecars.finalize_authentik_runtime_bundle",
        lambda *args, **kwargs: finalized_runtime,
    )
    monkeypatch.setattr("tests.auth_idp.sidecars.wait_for_healthchecks", lambda *args, **kwargs: None)
    monkeypatch.setattr("tests.auth_idp.sidecars.wait_for_gateway_listener", lambda *args, **kwargs: None)

    sidecar = start_authentik_sidecar(
        {"provider": "authentik"},
        services=RunningServices(
            url="http://127.0.0.1:8081",
            log_path=None,
            proc=None,
            config_path=None,
            docker_network_name="nmp-e2e-network",
            docker_container_alias="nmp-quickstart",
            docker_container_port=8080,
        ),
        config_hash="abc123",
        runtime_root=tmp_path,
    )

    assert port_calls == [
        (
            "gateway",
            8080,
            "authentik-e2e-abc123",
            {"AUTHENTIK_GATEWAY_PORT": "0", "AUTHENTIK_ISSUER_PORT": "0"},
        ),
        (
            "authentik-server",
            9000,
            "authentik-e2e-abc123",
            {"AUTHENTIK_GATEWAY_PORT": "0", "AUTHENTIK_ISSUER_PORT": "0"},
        ),
    ]
    assert up_calls == [{"AUTHENTIK_GATEWAY_PORT": "0", "AUTHENTIK_ISSUER_PORT": "0"}]
    assert down_calls == [{"AUTHENTIK_GATEWAY_PORT": "0", "AUTHENTIK_ISSUER_PORT": "0"}]
    assert sidecar.metadata == {
        "gateway_base_url": "http://127.0.0.1:38123",
        "discovery_url": "http://127.0.0.1:39123/application/o/nemo/.well-known/openid-configuration",
        "token_endpoint": "http://127.0.0.1:39123/application/o/token/",
    }
