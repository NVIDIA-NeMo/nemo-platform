# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


import e2e.services_pool as services_pool


def test_render_e2e_config_for_docker_preserves_container_paths(tmp_path) -> None:
    config = {
        "jobs": {
            "executors": [
                {
                    "provider": "subprocess",
                    "config": {"working_directory": "/data/subprocess-jobs"},
                }
            ]
        },
        "files": {"default_storage_config": {"type": "local", "path": "/data/files"}},
    }

    rendered = services_pool._render_e2e_config_for_backend(config, tmp_path, {"backend": "docker"})

    assert rendered["jobs"]["executors"][0]["config"]["working_directory"] == "/data/subprocess-jobs"
    assert rendered["files"]["default_storage_config"]["path"] == "/data/files"


def test_render_e2e_config_for_subprocess_rewrites_instance_paths(tmp_path) -> None:
    config = {
        "jobs": {
            "executors": [
                {
                    "provider": "subprocess",
                    "config": {"working_directory": ".tmp/e2e/subprocess-jobs"},
                }
            ]
        },
        "files": {"default_storage_config": {"type": "local", "path": ".tmp/e2e/files"}},
    }

    rendered = services_pool._render_e2e_config_for_backend(config, tmp_path, {"backend": "subprocess"})

    assert rendered["jobs"]["executors"][0]["config"]["working_directory"] == str(tmp_path / "subprocess-jobs")
    assert rendered["files"]["default_storage_config"]["path"] == str(tmp_path / "files")


def test_docker_backend_overrides_prefer_e2e_specific_env(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_REGISTRY", "ghcr.io/example/default")
    monkeypatch.setenv("BAKE_TAG", "default-tag")
    monkeypatch.setenv("NMP_E2E_IMAGE_REGISTRY", "ghcr.io/example/e2e")
    monkeypatch.setenv("NMP_E2E_IMAGE_TAG", "e2e-tag")

    overrides = services_pool._docker_backend_overrides()

    assert overrides == {
        "registry": "ghcr.io/example/e2e",
        "tag": "e2e-tag",
    }


def test_docker_backend_overrides_fall_back_to_ci_bake_env(monkeypatch) -> None:
    monkeypatch.delenv("NMP_E2E_IMAGE_REGISTRY", raising=False)
    monkeypatch.delenv("NMP_E2E_IMAGE_TAG", raising=False)
    monkeypatch.setenv("IMAGE_REGISTRY", "ghcr.io/example/default")
    monkeypatch.setenv("BAKE_TAG", "default-tag")

    overrides = services_pool._docker_backend_overrides()

    assert overrides == {
        "registry": "ghcr.io/example/default",
        "tag": "default-tag",
    }


def test_render_e2e_config_for_docker_compose_preserves_container_paths(tmp_path) -> None:
    config = {
        "jobs": {
            "executors": [
                {
                    "provider": "subprocess",
                    "config": {"working_directory": "/data/subprocess-jobs"},
                }
            ]
        },
        "files": {"default_storage_config": {"type": "local", "path": "/data/files"}},
    }

    rendered = services_pool._render_e2e_config_for_backend(config, tmp_path, {"backend": "docker_compose"})

    assert rendered["jobs"]["executors"][0]["config"]["working_directory"] == "/data/subprocess-jobs"
    assert rendered["files"]["default_storage_config"]["path"] == "/data/files"


def test_start_services_docker_compose_waits_for_auth_ready_when_enabled(tmp_path, monkeypatch) -> None:
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")

    class FakeDockerComposeBackend:
        def __init__(self, **kwargs) -> None:
            self.service_url = kwargs["service_url"]

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def write_logs(self, log_path) -> None:
            log_path.write_text("compose logs\n", encoding="utf-8")

    wait_calls = []

    def fake_wait_for_auth_ready(url, proc) -> bool:
        wait_calls.append((url, proc))
        return True

    monkeypatch.setattr(services_pool, "DockerComposeE2EBackend", FakeDockerComposeBackend)
    monkeypatch.setattr(services_pool, "_wait_for_auth_ready", fake_wait_for_auth_ready)

    services = services_pool._start_services_docker_compose(
        config_path,
        {"auth": {"enabled": True}},
        {
            "backend": "docker_compose",
            "compose_file": str(compose_file),
            "service_url": "http://127.0.0.1:8080",
            "lifecycle": "fresh",
        },
        "abc123",
        tmp_path / "services.log",
    )

    assert wait_calls == [("http://127.0.0.1:8080", None)]
    assert services.auth_enabled is True
    assert services.url == "http://127.0.0.1:8080"


def test_start_services_docker_compose_uses_auth_ready_url_when_configured(tmp_path, monkeypatch) -> None:
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")

    class FakeDockerComposeBackend:
        def __init__(self, **kwargs) -> None:
            self.service_url = kwargs["service_url"]

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def write_logs(self, log_path) -> None:
            log_path.write_text("compose logs\n", encoding="utf-8")

    wait_calls = []

    def fake_wait_for_auth_ready(url, proc) -> bool:
        wait_calls.append((url, proc))
        return True

    monkeypatch.setattr(services_pool, "DockerComposeE2EBackend", FakeDockerComposeBackend)
    monkeypatch.setattr(services_pool, "_wait_for_auth_ready", fake_wait_for_auth_ready)

    services = services_pool._start_services_docker_compose(
        config_path,
        {"auth": {"enabled": True}},
        {
            "backend": "docker_compose",
            "compose_file": str(compose_file),
            "service_url": "http://127.0.0.1:38080",
            "auth_ready_url": "http://127.0.0.1:38081",
            "lifecycle": "fresh",
        },
        "abc123",
        tmp_path / "services.log",
    )

    assert wait_calls == [("http://127.0.0.1:38081", None)]
    assert services.auth_enabled is True
    assert services.url == "http://127.0.0.1:38080"


def test_start_services_docker_compose_exposes_log_path_and_captures_logs_on_close(tmp_path, monkeypatch) -> None:
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    log_path = tmp_path / "services.log"
    events = []

    class FakeDockerComposeBackend:
        def __init__(self, **kwargs) -> None:
            self.service_url = kwargs["service_url"]

        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

        def write_logs(self, path) -> None:
            events.append(("logs", path))
            path.write_text("compose logs\n", encoding="utf-8")

    monkeypatch.setattr(services_pool, "DockerComposeE2EBackend", FakeDockerComposeBackend)

    services = services_pool._start_services_docker_compose(
        config_path,
        {},
        {
            "backend": "docker_compose",
            "compose_file": str(compose_file),
            "service_url": "http://127.0.0.1:38080",
            "lifecycle": "fresh",
        },
        "abc123",
        log_path,
    )

    assert services.log_path == log_path
    assert services.close is not None

    services.close()

    assert events == ["start", ("logs", log_path), "stop"]
    assert log_path.read_text(encoding="utf-8") == "compose logs\n"
