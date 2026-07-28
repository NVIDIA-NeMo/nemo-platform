# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side launcher for the default Experimentalist OpenShell runtime."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

DEFAULT_IMAGE = "local/nmp-experimentalist:local"
IMAGE_ENV = "NEMO_EXPERIMENTALIST_IMAGE"
PLATFORM_ENV = "NEMO_EXPERIMENTALIST_PLATFORM"
OUTPUT_DIR_ENV = "NEMO_EXPERIMENTALIST_OUTPUT_DIR"
RUNTIME_IMAGE_LABEL = "com.nvidia.nemo.experimentalist.openshell-runtime"
RUNTIME_IMAGE_API = "1"


class OpenShellLaunchError(RuntimeError):
    """Raised when the fail-closed OpenShell launch cannot be prepared."""


def _find_repo_root(*starts: Path) -> Path | None:
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / "docker-bake.hcl").is_file() and (
                candidate / "plugins" / "nemo-experimentalist" / "Dockerfile"
            ).is_file():
                return candidate
    return None


def _host_platform(machine: str | None = None) -> str:
    normalized = (machine or platform.machine()).strip().lower()
    if normalized in {"aarch64", "arm64"}:
        return "linux/arm64"
    if normalized in {"amd64", "x86_64"}:
        return "linux/amd64"
    raise OpenShellLaunchError(
        f"Unsupported host architecture {normalized!r}; set {PLATFORM_ENV} to linux/arm64 or linux/amd64"
    )


def _container_platform_url(value: str) -> str:
    """Rewrite a host loopback URL for a Docker-backed OpenShell sandbox."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise OpenShellLaunchError(f"Invalid NeMo Platform URL: {value}") from exc
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return value
    if parsed.username is not None or parsed.password is not None:
        raise OpenShellLaunchError("NeMo Platform URL must not contain user information")
    port_suffix = f":{port}" if port is not None else ""
    return urlunsplit((parsed.scheme, f"host.docker.internal{port_suffix}", parsed.path, parsed.query, parsed.fragment))


def _acquire_default_image(
    *,
    docker: str,
    image: str,
    workspace_dir: Path,
    runtime_env: dict[str, str],
) -> None:
    inspected = subprocess.run(  # noqa: S603
        [
            docker,
            "image",
            "inspect",
            "--format",
            f'{{{{ index .Config.Labels "{RUNTIME_IMAGE_LABEL}" }}}}',
            image,
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        stderr=subprocess.DEVNULL,
    )
    if inspected.returncode == 0 and inspected.stdout.strip() == RUNTIME_IMAGE_API:
        return

    repo_root = _find_repo_root(workspace_dir, Path(__file__).resolve())
    if repo_root is None:
        raise OpenShellLaunchError(
            f"A compatible Experimentalist image {image!r} is not available locally. "
            f"Set {IMAGE_ENV} to a published image, or run from a nemo-platform source checkout "
            "so the CLI can build it."
        )

    selected_platform = runtime_env.get(PLATFORM_ENV, "").strip() or _host_platform()
    if selected_platform not in {"linux/arm64", "linux/amd64"}:
        raise OpenShellLaunchError(f"{PLATFORM_ENV} must be linux/arm64 or linux/amd64")
    build_env = {
        **runtime_env,
        "IMAGE_REGISTRY": "local",
        "BAKE_TAG": "local",
        "BUILD_ARCH": selected_platform,
    }
    built = subprocess.run(  # noqa: S603
        [docker, "buildx", "bake", "nmp-experimentalist-docker", "--load"],
        cwd=repo_root,
        env=build_env,
        check=False,
    )
    if built.returncode != 0:
        raise OpenShellLaunchError(
            f"Could not build {image!r} for {selected_platform}; set {IMAGE_ENV} to a usable published or local image"
        )


def launch_in_openshell(
    command: Literal["run", "doctor"],
    forwarded_args: list[str],
    *,
    workspace_dir: Path,
    output_dir: Path | None = None,
    platform_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Launch one Experimentalist command inside OpenShell without local fallback."""
    workspace = workspace_dir.expanduser().resolve()
    if not workspace.is_dir():
        raise OpenShellLaunchError(f"OpenShell workspace directory not found: {workspace}")
    if not workspace.name:
        raise OpenShellLaunchError("The filesystem root cannot be used as an OpenShell workspace")

    runtime_env = dict(os.environ if env is None else env)
    openshell = shutil.which("openshell", path=runtime_env.get("PATH"))
    if openshell is None:
        raise OpenShellLaunchError(
            "OpenShell is the default Experimentalist runtime but its CLI is not on PATH. "
            "Install and configure OpenShell before running Experimentalist."
        )

    image = runtime_env.get(IMAGE_ENV, "").strip() or DEFAULT_IMAGE
    runtime_env[IMAGE_ENV] = image
    if image == DEFAULT_IMAGE:
        docker = shutil.which("docker", path=runtime_env.get("PATH"))
        if docker is None:
            raise OpenShellLaunchError(
                f"Default image {image!r} requires Docker for local image discovery/build. "
                f"Set {IMAGE_ENV} to an image available to the OpenShell gateway."
            )
        _acquire_default_image(
            docker=docker,
            image=image,
            workspace_dir=workspace,
            runtime_env=runtime_env,
        )

    if output_dir is not None:
        runtime_env[OUTPUT_DIR_ENV] = str(output_dir.expanduser().resolve())
    if platform_url:
        runtime_env["NMP_BASE_URL"] = _container_platform_url(platform_url)

    script_path = Path(__file__).with_name("run.sh")
    if not script_path.is_file():
        raise OpenShellLaunchError(f"Packaged OpenShell launcher is missing: {script_path}")

    completed = subprocess.run(  # noqa: S603
        [str(script_path), str(workspace), command, *forwarded_args],
        env=runtime_env,
        check=False,
    )
    return completed.returncode
