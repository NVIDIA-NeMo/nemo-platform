# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


import e2e.services_pool as services_pool


def test_render_e2e_config_for_docker_preserves_container_paths(tmp_path) -> None:
    config = {
        "e2e": {"backend": "docker"},
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

    rendered = services_pool._render_e2e_config_for_backend(config, tmp_path)

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

    rendered = services_pool._render_e2e_config_for_backend(config, tmp_path)

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
