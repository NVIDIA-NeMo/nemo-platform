# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
from pathlib import Path

import pytest

from e2e.backends.docker_compose import DockerComposeE2EBackend


def _compose_ps_json(*entries: dict[str, str]) -> str:
    return json.dumps(list(entries))


def test_compose_backend_injects_generated_nemo_config_path(monkeypatch, tmp_path: Path) -> None:
    commands: list[tuple[list[str], dict[str, str] | None]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")

    def fake_run(args, *, check, text=False, capture_output=False, env=None):
        commands.append((list(args), env))
        stdout = ""
        if capture_output and "config" in args:
            stdout = "nemo\ngateway\nauthentik-server\nauthentik-worker\nauthentik-postgres\nauthentik-redis\n"
        if capture_output and "ps" in args:
            stdout = _compose_ps_json(
                {"Service": "nemo", "State": "running"},
                {"Service": "gateway", "State": "running"},
                {"Service": "authentik-server", "State": "running", "Health": "healthy"},
                {"Service": "authentik-worker", "State": "running", "Health": "healthy"},
                {"Service": "authentik-postgres", "State": "running", "Health": "healthy"},
                {"Service": "authentik-redis", "State": "running", "Health": "healthy"},
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    class Response:
        status_code = 200

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)
    monkeypatch.setattr("e2e.backends.docker_compose.httpx.get", lambda *args, **kwargs: Response())

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
        wait_url="http://127.0.0.1:38080/apis/auth/discovery",
        env={"AUTHENTIK_GATEWAY_PORT": "38080"},
    )

    backend.start()

    assert commands
    first_env = commands[0][1]
    assert first_env is not None
    assert first_env["AUTHENTIK_GATEWAY_PORT"] == "38080"
    assert first_env["NEMO_COMPOSE_CONFIG_PATH"] == str(config_path.resolve())


def test_compose_backend_stop_uses_same_project_and_env(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")

    def fake_run(args, *, check, text=False, capture_output=False, env=None):
        calls.append((list(args), env))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
        env={"AUTHENTIK_GATEWAY_PORT": "38080"},
    )

    backend.stop()

    args, env = calls[0]
    assert args[:6] == ["docker", "compose", "-f", str(compose_file), "-p", "authentik-e2e-test"]
    assert args[6:] == ["down", "-v"]
    assert env is not None
    assert env["AUTHENTIK_GATEWAY_PORT"] == "38080"
    assert env["NEMO_COMPOSE_CONFIG_PATH"] == str(config_path.resolve())


def test_compose_backend_write_logs_uses_same_project_and_env(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")
    log_path = tmp_path / "compose.log"

    def fake_run(args, *, check, text=False, stdout=None, stderr=None, env=None, **_kwargs):
        calls.append((list(args), env))
        assert stdout is not None
        stdout.write("nemo log line\n")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
        env={"AUTHENTIK_GATEWAY_PORT": "38080"},
    )

    backend.write_logs(log_path)

    args, env = calls[0]
    assert args[:6] == ["docker", "compose", "-f", str(compose_file), "-p", "authentik-e2e-test"]
    assert args[6:] == ["logs", "--no-color", "--timestamps"]
    assert env is not None
    assert env["AUTHENTIK_GATEWAY_PORT"] == "38080"
    assert env["NEMO_COMPOSE_CONFIG_PATH"] == str(config_path.resolve())
    assert log_path.read_text(encoding="utf-8") == "nemo log line\n"


def test_compose_backend_reuse_mode_reuses_healthy_stack_without_restart(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")

    def fake_run(args, *, check, text=False, capture_output=False, env=None):
        calls.append((list(args), env))
        stdout = ""
        if capture_output and "config" in args:
            stdout = "nemo\ngateway\n"
        if args[6:] == ["ps", "--services", "--status", "running"]:
            raise AssertionError("compose readiness should use health-aware ps json, not running-only services")
        if capture_output and "ps" in args:
            stdout = _compose_ps_json(
                {"Service": "nemo", "State": "running"},
                {"Service": "gateway", "State": "running"},
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    class Response:
        status_code = 200

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)
    monkeypatch.setattr("e2e.backends.docker_compose.httpx.get", lambda *args, **kwargs: Response())

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
        wait_url="http://127.0.0.1:38080/apis/auth/discovery",
        lifecycle="reuse",
    )

    backend.start()

    assert [args[6:] for args, _env in calls] == [
        ["config", "--services"],
        ["ps", "--all", "--format", "json"],
    ]


def test_compose_backend_fails_when_compose_config_discovers_no_services(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")

    def fake_run(args, *, check, text=False, capture_output=False, env=None):
        calls.append(list(args))
        if capture_output and args[6:] == ["config", "--services"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected compose command after empty service discovery: {args[6:]}")

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
    )

    with pytest.raises(RuntimeError, match="no services were discovered"):
        backend.start()

    assert [args[6:] for args in calls] == [["config", "--services"]]


def test_compose_backend_waits_for_healthy_services_before_ready_probe(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")
    readiness_checks = 0
    ready_probe_calls = 0

    def fake_run(args, *, check, text=False, capture_output=False, env=None):
        nonlocal readiness_checks
        calls.append((list(args), env))
        stdout = ""
        if capture_output and "config" in args:
            stdout = "nemo\ngateway\n"
        if args[6:] == ["ps", "--services", "--status", "running"]:
            raise AssertionError("compose readiness should use health-aware ps json, not running-only services")
        if capture_output and "ps" in args:
            readiness_checks += 1
            stdout = (
                _compose_ps_json(
                    {"Service": "nemo", "State": "running"},
                    {"Service": "gateway", "State": "running", "Health": "starting"},
                )
                if readiness_checks == 1
                else _compose_ps_json(
                    {"Service": "nemo", "State": "running"},
                    {"Service": "gateway", "State": "running", "Health": "healthy"},
                )
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    class Response:
        status_code = 200

    def fake_get(*args, **kwargs):
        nonlocal ready_probe_calls
        ready_probe_calls += 1
        assert readiness_checks == 2
        return Response()

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)
    monkeypatch.setattr("e2e.backends.docker_compose.httpx.get", fake_get)
    monkeypatch.setattr("e2e.backends.docker_compose.time.sleep", lambda _seconds: None)

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
    )

    backend.start()

    assert ready_probe_calls == 1
    assert [args[6:] for args, _env in calls] == [
        ["config", "--services"],
        ["down", "-v"],
        ["up", "-d"],
        ["ps", "--all", "--format", "json"],
        ["ps", "--all", "--format", "json"],
    ]


def test_compose_backend_stop_is_noop_in_reuse_mode(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n")
    config_path = tmp_path / "platform.yaml"
    config_path.write_text("platform: {}\n")

    def fake_run(args, *, check, text=False, capture_output=False, env=None):
        calls.append((list(args), env))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("e2e.backends.docker_compose.subprocess.run", fake_run)

    backend = DockerComposeE2EBackend(
        compose_file=compose_file,
        config_path=config_path,
        project_name="authentik-e2e-test",
        service_url="http://127.0.0.1:38080",
        lifecycle="reuse",
    )

    backend.stop()

    assert calls == []
