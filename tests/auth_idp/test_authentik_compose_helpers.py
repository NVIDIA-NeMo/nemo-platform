# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess

import httpx
import pytest

from tests.auth_idp.compose import (
    collect_compose_diagnostics,
    compose_down,
    compose_published_port,
    compose_up,
    wait_for_healthchecks,
    wait_for_token_endpoint,
)
from tests.auth_idp.providers import ProviderConfig

pytestmark = [pytest.mark.auth_idp]


def test_compose_up_uses_wait_timeout(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTHENTIK_E2E_LIFECYCLE", raising=False)
    calls: list[list[str]] = []
    envs: list[dict[str, str] | None] = []
    running_checks = 0

    def fake_run(args, check, capture_output=False, text=False, env=None):
        nonlocal running_checks
        calls.append(args)
        envs.append(env)
        if args[-2:] == ["config", "--services"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway\nauthentik-server\n")
        if args[-4:] == ["ps", "--services", "--status", "running"]:
            running_checks += 1
            stdout = "gateway\n" if running_checks == 1 else "gateway\nauthentik-server\n"
            return subprocess.CompletedProcess(args, 0, stdout=stdout)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("tests.auth_idp.compose.subprocess.run", fake_run)
    monkeypatch.setattr("tests.auth_idp.compose.time.sleep", lambda _: None)

    compose_up(tmp_path / "docker-compose.yml", project_name="authentik-e2e-test", wait_timeout=240)

    assert ["config", "--services"] == calls[0][-2:]
    assert calls[1] == [
        "docker",
        "compose",
        "-f",
        str(tmp_path / "docker-compose.yml"),
        "-p",
        "authentik-e2e-test",
        "up",
        "-d",
    ]
    assert calls[2][-4:] == ["ps", "--services", "--status", "running"]
    assert calls[3] == calls[1]
    assert calls[4][-4:] == ["ps", "--services", "--status", "running"]
    assert all(env is not None for env in envs)


def test_compose_up_supports_base_and_override_files(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTHENTIK_E2E_LIFECYCLE", raising=False)
    calls: list[list[str]] = []
    envs: list[dict[str, str] | None] = []

    def fake_run(args, check, capture_output=False, text=False, env=None):
        calls.append(args)
        envs.append(env)
        if args[-2:] == ["config", "--services"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway\n")
        if args[-4:] == ["ps", "--services", "--status", "running"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway\n")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("tests.auth_idp.compose.subprocess.run", fake_run)

    compose_up(
        (tmp_path / "docker-compose.yml", tmp_path / "docker-compose.override.yml"),
        project_name="authentik-e2e-test",
        wait_timeout=30,
        env={"AUTHENTIK_GATEWAY_PORT": "0"},
    )

    assert ["config", "--services"] == calls[0][-2:]
    assert calls[1] == [
        "docker",
        "compose",
        "-f",
        str(tmp_path / "docker-compose.yml"),
        "-f",
        str(tmp_path / "docker-compose.override.yml"),
        "-p",
        "authentik-e2e-test",
        "up",
        "-d",
    ]
    assert envs[1]["AUTHENTIK_GATEWAY_PORT"] == "0"


def test_compose_up_reuse_mode_skips_restart_for_healthy_stack(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(args, check, capture_output=False, text=False, env=None):
        calls.append(args)
        if args[-2:] == ["config", "--services"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway\nauthentik-server\n")
        if args[-4:] == ["ps", "--services", "--status", "running"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway\nauthentik-server\n")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("tests.auth_idp.compose.subprocess.run", fake_run)
    monkeypatch.setattr("tests.auth_idp.compose.httpx.get", lambda *args, **kwargs: httpx.Response(200))

    compose_up(
        tmp_path / "docker-compose.yml",
        project_name="authentik-e2e-test",
        wait_timeout=30,
        env={"AUTHENTIK_E2E_LIFECYCLE": "reuse"},
    )

    assert calls == [
        [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "-p",
            "authentik-e2e-test",
            "config",
            "--services",
        ],
        [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "-p",
            "authentik-e2e-test",
            "ps",
            "--services",
            "--status",
            "running",
        ],
    ]


def test_compose_down_is_noop_in_reuse_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTHENTIK_E2E_LIFECYCLE", raising=False)
    calls: list[list[str]] = []

    def fake_run(args, check, capture_output=False, text=False, env=None):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("tests.auth_idp.compose.subprocess.run", fake_run)

    compose_down(
        tmp_path / "docker-compose.yml",
        project_name="authentik-e2e-test",
        env={"AUTHENTIK_E2E_LIFECYCLE": "reuse"},
    )

    assert calls == []


def test_wait_for_token_endpoint_retries_until_machine_grant_succeeds(monkeypatch):
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=None,
        gateway_base_url="http://127.0.0.1:18080",
        issuer_url="http://authentik-server:9000/application/o/nemo/",
        discovery_url="http://127.0.0.1:18080/application/o/nemo/.well-known/openid-configuration",
        nemo_config=None,  # type: ignore[arg-type]
        workload_principal_id="svc-nemo-ci",
        workload_expected_groups=["nemo-editors"],
        workload_audience="nemo-platform",
        workload_principal_claim="sub",
        workload_groups_claim="groups",
        workload_groups_format="comma_string",
        workload_token_env_vars=["NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE"],
        workload_forwarded_headers={
            "principal_id": "X-NMP-Principal-Id",
            "principal_groups": "X-NMP-Principal-Groups",
        },
        token_endpoint="http://127.0.0.1:18080/application/o/token/",
        human_grant={"grant_type": "password"},
        machine_grant={
            "grant_type": "password",
            "client_id": "nemo-platform",
            "client_secret": "secret",
            "username": "svc-nemo-ci",
            "password": "svc-nemo-ci-token-secret-dev",
            "scope": "openid email groups",
        },
        healthchecks=[],
        startup_timeouts={},
    )

    responses = [
        httpx.Response(502, request=httpx.Request("POST", provider.token_endpoint)),
        httpx.Response(200, json={"access_token": "ok"}, request=httpx.Request("POST", provider.token_endpoint)),
    ]

    def fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("tests.auth_idp.compose.time.sleep", lambda _: None)

    token = wait_for_token_endpoint(provider, timeout=1)
    assert token == "ok"


def test_wait_for_token_endpoint_retries_request_errors_until_machine_grant_succeeds(monkeypatch):
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=None,
        gateway_base_url="http://127.0.0.1:18080",
        issuer_url="http://authentik-server:9000/application/o/nemo/",
        discovery_url="http://127.0.0.1:18080/application/o/nemo/.well-known/openid-configuration",
        nemo_config=None,  # type: ignore[arg-type]
        workload_principal_id="svc-nemo-ci",
        workload_expected_groups=["nemo-editors"],
        workload_audience="nemo-platform",
        workload_principal_claim="sub",
        workload_groups_claim="groups",
        workload_groups_format="comma_string",
        workload_token_env_vars=["NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE"],
        workload_forwarded_headers={
            "principal_id": "X-NMP-Principal-Id",
            "principal_groups": "X-NMP-Principal-Groups",
        },
        token_endpoint="http://127.0.0.1:18080/application/o/token/",
        human_grant={"grant_type": "password"},
        machine_grant={
            "grant_type": "password",
            "client_id": "nemo-platform",
            "client_secret": "secret",
            "username": "svc-nemo-ci",
            "password": "svc-nemo-ci-token-secret-dev",
            "scope": "openid email groups",
        },
        healthchecks=[],
        startup_timeouts={},
    )

    request = httpx.Request("POST", provider.token_endpoint)
    responses = [
        httpx.ConnectError("connection refused", request=request),
        httpx.Response(200, json={"access_token": "ok"}, request=request),
    ]

    def fake_post(*args, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("tests.auth_idp.compose.time.sleep", lambda _: None)

    token = wait_for_token_endpoint(provider, timeout=1)
    assert token == "ok"


def test_wait_for_healthchecks_gives_each_http_check_its_own_deadline(monkeypatch):
    provider = ProviderConfig(
        name="authentik",
        mode="compose-ci",
        compose_file=None,
        gateway_base_url="http://127.0.0.1:18080",
        issuer_url="http://authentik-server:9000/application/o/nemo/",
        discovery_url="http://127.0.0.1:18080/application/o/nemo/.well-known/openid-configuration",
        nemo_config=None,  # type: ignore[arg-type]
        workload_principal_id="svc-nemo-ci",
        workload_expected_groups=["nemo-editors"],
        workload_audience="nemo-platform",
        workload_principal_claim="sub",
        workload_groups_claim="groups",
        workload_groups_format="comma_string",
        workload_token_env_vars=["NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE"],
        workload_forwarded_headers={
            "principal_id": "X-NMP-Principal-Id",
            "principal_groups": "X-NMP-Principal-Groups",
        },
        token_endpoint="http://127.0.0.1:18080/application/o/token/",
        human_grant={"grant_type": "password"},
        machine_grant={"grant_type": "password", "username": "svc-nemo-ci", "password": "svc-nemo-ci-token-secret-dev"},
        healthchecks=[
            {"kind": "http", "url": "http://127.0.0.1:18080/first"},
            {"kind": "http", "url": "http://127.0.0.1:18080/second"},
        ],
        startup_timeouts={},
    )

    now = 100.0
    responses = {
        "http://127.0.0.1:18080/first": [503, 200],
        "http://127.0.0.1:18080/second": [503, 200],
    }

    def fake_monotonic():
        return now

    def fake_sleep(seconds):
        nonlocal now
        now += seconds

    def fake_get(url, timeout):
        status_code = responses[url].pop(0)
        return httpx.Response(status_code, request=httpx.Request("GET", url))

    monkeypatch.setattr("tests.auth_idp.compose.time.monotonic", fake_monotonic)
    monkeypatch.setattr("tests.auth_idp.compose.time.sleep", fake_sleep)
    monkeypatch.setattr(httpx, "get", fake_get)

    wait_for_healthchecks(provider, timeout=3)


def test_collect_compose_diagnostics_writes_ps_and_logs(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    envs: list[dict[str, str] | None] = []

    def fake_run(args, check, capture_output=False, text=False, env=None):
        calls.append(args)
        envs.append(env)
        if args[-2:] == ["ps", "--all"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway\nauthentik-server\n", stderr="")
        if args[-2:] == ["logs", "--no-color"]:
            return subprocess.CompletedProcess(args, 0, stdout="gateway log line\n", stderr="warning line\n")
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr("tests.auth_idp.compose.subprocess.run", fake_run)
    monkeypatch.setenv("E2E_SERVICES_LOG_DIR", str(tmp_path))

    output_dir = collect_compose_diagnostics(
        tmp_path / "docker-compose.yml",
        project_name="authentik-e2e-test",
    )

    assert output_dir == tmp_path
    assert calls == [
        [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "-p",
            "authentik-e2e-test",
            "ps",
            "--all",
        ],
        [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "-p",
            "authentik-e2e-test",
            "logs",
            "--no-color",
        ],
    ]
    assert (tmp_path / "authentik-e2e-test.ps.txt").read_text() == "gateway\nauthentik-server\n"
    assert (tmp_path / "authentik-e2e-test.logs.txt").read_text() == "gateway log line\n\n[stderr]\nwarning line\n"
    assert all(env is not None for env in envs)


def test_compose_published_port_reads_docker_assigned_host_port(monkeypatch, tmp_path):
    def fake_run(args, check, capture_output=False, text=False, env=None):
        assert args == [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "-p",
            "authentik-e2e-test",
            "port",
            "gateway",
            "8080",
        ]
        assert env is not None
        return subprocess.CompletedProcess(args, 0, stdout="127.0.0.1:38123\n", stderr="")

    monkeypatch.setattr("tests.auth_idp.compose.subprocess.run", fake_run)

    assert (
        compose_published_port(
            tmp_path / "docker-compose.yml",
            "gateway",
            8080,
            project_name="authentik-e2e-test",
        )
        == 38123
    )
