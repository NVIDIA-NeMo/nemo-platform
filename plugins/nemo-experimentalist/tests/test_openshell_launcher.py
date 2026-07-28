# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.openshell import launcher


def _completed(
    argv: object,
    returncode: int = 0,
    stdout: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout)


def test_custom_image_launches_without_host_docker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def which(name: str, *, path: str | None = None) -> str | None:
        assert path == "/test/bin"
        return "/test/bin/openshell" if name == "openshell" else None

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((argv, kwargs))
        return _completed(argv)

    monkeypatch.setattr(launcher.shutil, "which", which)
    monkeypatch.setattr(launcher.subprocess, "run", run)

    result = launcher.launch_in_openshell(
        "doctor",
        ["--insight", "insight-1"],
        workspace_dir=tmp_path,
        platform_url="http://localhost:8080",
        env={
            "PATH": "/test/bin",
            launcher.IMAGE_ENV: "registry.example/experimentalist:v1",
        },
    )

    assert result == 0
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        str(Path(launcher.__file__).with_name("run.sh")),
        str(tmp_path),
        "doctor",
        "--insight",
        "insight-1",
    ]
    assert kwargs["env"] == {
        "PATH": "/test/bin",
        launcher.IMAGE_ENV: "registry.example/experimentalist:v1",
        "NMP_BASE_URL": "http://host.docker.internal:8080",
    }


def test_missing_default_image_builds_for_selected_host_platform(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    workspace = tmp_path / "workspace"
    repo_root.mkdir()
    workspace.mkdir()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def which(name: str, *, path: str | None = None) -> str | None:
        assert path == "/test/bin"
        return f"/test/bin/{name}"

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((argv, kwargs))
        return _completed(argv, returncode=1 if argv[1:3] == ["image", "inspect"] else 0)

    monkeypatch.setattr(launcher.shutil, "which", which)
    monkeypatch.setattr(launcher.subprocess, "run", run)
    monkeypatch.setattr(launcher, "_find_repo_root", lambda *starts: repo_root)

    result = launcher.launch_in_openshell(
        "run",
        ["--no-insight"],
        workspace_dir=workspace,
        output_dir=workspace / "output",
        env={
            "PATH": "/test/bin",
            launcher.PLATFORM_ENV: "linux/arm64",
        },
    )

    assert result == 0
    assert calls[0][0] == [
        "/test/bin/docker",
        "image",
        "inspect",
        "--format",
        f'{{{{ index .Config.Labels "{launcher.RUNTIME_IMAGE_LABEL}" }}}}',
        launcher.DEFAULT_IMAGE,
    ]
    assert calls[1][0] == [
        "/test/bin/docker",
        "buildx",
        "bake",
        "nmp-experimentalist-docker",
        "--load",
    ]
    assert calls[1][1]["cwd"] == repo_root
    assert calls[1][1]["env"] == {
        "PATH": "/test/bin",
        launcher.PLATFORM_ENV: "linux/arm64",
        launcher.IMAGE_ENV: launcher.DEFAULT_IMAGE,
        "IMAGE_REGISTRY": "local",
        "BAKE_TAG": "local",
        "BUILD_ARCH": "linux/arm64",
    }
    assert calls[2][1]["env"][launcher.OUTPUT_DIR_ENV] == str((workspace / "output").resolve())


def test_compatible_default_image_is_reused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def which(name: str, *, path: str | None = None) -> str | None:
        assert path == "/test/bin"
        return f"/test/bin/{name}"

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            return _completed(argv, stdout=f"{launcher.RUNTIME_IMAGE_API}\n")
        return _completed(argv)

    monkeypatch.setattr(launcher.shutil, "which", which)
    monkeypatch.setattr(launcher.subprocess, "run", run)

    result = launcher.launch_in_openshell(
        "doctor",
        [],
        workspace_dir=tmp_path,
        env={"PATH": "/test/bin"},
    )

    assert result == 0
    assert len(calls) == 2
    assert calls[0][1:3] == ["image", "inspect"]
    assert calls[1][0] == str(Path(launcher.__file__).with_name("run.sh"))


def test_missing_openshell_fails_without_local_fallback(tmp_path: Path) -> None:
    with pytest.raises(launcher.OpenShellLaunchError, match="default Experimentalist runtime"):
        launcher.launch_in_openshell(
            "doctor",
            [],
            workspace_dir=tmp_path,
            env={"PATH": ""},
        )


@pytest.mark.parametrize(
    ("host_url", "container_url"),
    [
        ("http://localhost:8080", "http://host.docker.internal:8080"),
        ("https://127.0.0.1/api", "https://host.docker.internal/api"),
        ("http://[::1]:9000/ready", "http://host.docker.internal:9000/ready"),
        ("https://platform.example/api", "https://platform.example/api"),
    ],
)
def test_container_platform_url_rewrites_only_loopback(host_url: str, container_url: str) -> None:
    assert launcher._container_platform_url(host_url) == container_url


def test_container_platform_url_rejects_invalid_port() -> None:
    with pytest.raises(launcher.OpenShellLaunchError, match="Invalid NeMo Platform URL"):
        launcher._container_platform_url("http://localhost:not-a-port")
