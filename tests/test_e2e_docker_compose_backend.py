# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
from pathlib import Path

from e2e.backends.docker_compose import DockerComposeE2EBackend


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
            stdout = "nemo\ngateway\nauthentik-server\nauthentik-worker\nauthentik-postgres\nauthentik-redis\n"
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
        if capture_output and "ps" in args:
            stdout = "nemo\ngateway\n"
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
        env={"AUTHENTIK_E2E_LIFECYCLE": "reuse"},
    )

    backend.start()

    assert [args[6:] for args, _env in calls] == [
        ["config", "--services"],
        ["ps", "--services", "--status", "running"],
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
        env={"AUTHENTIK_E2E_LIFECYCLE": "reuse"},
    )

    backend.stop()

    assert calls == []
