# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side launcher for the default Experimentalist OpenShell runtime."""

from __future__ import annotations

import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_IMAGE = "local/nmp-experimentalist:local"
IMAGE_ENV = "NEMO_EXPERIMENTALIST_IMAGE"
PLATFORM_ENV = "NEMO_EXPERIMENTALIST_PLATFORM"
OUTPUT_DIR_ENV = "NEMO_EXPERIMENTALIST_OUTPUT_DIR"
RUNTIME_IMAGE_LABEL = "com.nvidia.nemo.experimentalist.openshell-runtime"
RUNTIME_IMAGE_API = "1"
BRIDGE_TOKEN_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN"
BRIDGE_URL_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL"
DEFAULT_BRIDGE_HOST_URL = "http://127.0.0.1:8765"
DEFAULT_BRIDGE_CONTAINER_URL = "http://host.docker.internal:8765"
DEFAULT_SMART_MODEL = "openai/openai/openai/gpt-5.5"


class OpenShellLaunchError(RuntimeError):
    """Raised when the fail-closed OpenShell launch cannot be prepared."""


@dataclass
class _ManagedBridge:
    process: subprocess.Popen[bytes]
    log_path: Path
    log_handle: BinaryIO

    def stop(self) -> None:
        """Stop only the bridge process created for this launch."""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.log_handle.close()


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


def _bridge_ready(url: str) -> bool:
    try:
        return httpx.get(f"{url.rstrip('/')}/health/ready", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


def _host_bridge_url(value: str) -> str:
    """Translate the Docker host alias back to loopback for host-side probes."""
    parsed = urlsplit(value)
    if parsed.hostname != "host.docker.internal":
        return value
    port_suffix = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"127.0.0.1{port_suffix}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _start_bridge(
    *,
    workspace: Path,
    runtime_env: dict[str, str],
) -> _ManagedBridge | None:
    """Reuse an explicitly configured bridge or start an ephemeral local one."""
    configured_url = runtime_env.get(BRIDGE_URL_ENV, "").strip()
    token = runtime_env.get(BRIDGE_TOKEN_ENV, "").strip()
    host_url = _host_bridge_url(configured_url) if configured_url else DEFAULT_BRIDGE_HOST_URL
    if configured_url:
        if not token:
            raise OpenShellLaunchError(f"{BRIDGE_TOKEN_ENV} is required with an explicit {BRIDGE_URL_ENV}")
        if not _bridge_ready(host_url):
            raise OpenShellLaunchError(f"Configured Harbor bridge is not ready: {host_url}")
        return None
    if _bridge_ready(host_url):
        if not token:
            raise OpenShellLaunchError(
                f"A Harbor bridge is already listening at {host_url}, but {BRIDGE_TOKEN_ENV} "
                "is not set. Stop it or export its token."
            )
        runtime_env[BRIDGE_URL_ENV] = DEFAULT_BRIDGE_CONTAINER_URL
        return None

    token = token or secrets.token_urlsafe(32)
    runtime_env[BRIDGE_TOKEN_ENV] = token
    runtime_env[BRIDGE_URL_ENV] = DEFAULT_BRIDGE_CONTAINER_URL
    runtime_root = workspace / "tmp" / "experimentalist-openshell"
    storage_root = runtime_root / "bridge"
    runtime_root.mkdir(parents=True, exist_ok=True)
    log_path = runtime_root / "bridge.log"
    log_handle = log_path.open("ab")
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "nemo_experimentalist_plugin.harbor_bridge.service",
            "--host",
            "0.0.0.0",
            "--port",
            "8765",
            "--storage-root",
            str(storage_root),
        ],
        cwd=workspace,
        env=runtime_env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    managed = _ManagedBridge(process=process, log_path=log_path, log_handle=log_handle)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            managed.stop()
            detail = log_path.read_text(encoding="utf-8", errors="replace").strip()
            raise OpenShellLaunchError(
                "The Experimentalist Harbor bridge exited before becoming ready" + (f": {detail}" if detail else "")
            )
        if _bridge_ready(host_url):
            return managed
        time.sleep(0.2)
    managed.stop()
    raise OpenShellLaunchError(f"The Experimentalist Harbor bridge did not become ready at {host_url}; see {log_path}")


def _configure_providers(runtime_env: dict[str, str]) -> None:
    """Create the dedicated OpenShell providers used by this runtime."""
    source_control = runtime_env.get("NEMO_EXPERIMENTALIST_SOURCE_CONTROL", "none")
    if source_control.startswith("gitlab-") and not runtime_env.get("GITLAB_TOKEN"):
        raise OpenShellLaunchError(
            "This profile uses a GitLab dataset registry. Add GITLAB_TOKEN to the "
            "profile's ignored .env file, then rerun the command."
        )
    if source_control.startswith("github-") and not (runtime_env.get("GH_TOKEN") or runtime_env.get("GITHUB_TOKEN")):
        raise OpenShellLaunchError(
            "This profile uses a GitHub dataset registry. Add GH_TOKEN to the "
            "profile's ignored .env file, then rerun the command."
        )
    script_path = Path(__file__).with_name("configure-providers.sh")
    if not script_path.is_file():
        raise OpenShellLaunchError(f"Packaged provider setup is missing: {script_path}")
    completed = subprocess.run(  # noqa: S603
        [str(script_path)],
        env=runtime_env,
        check=False,
    )
    if completed.returncode != 0:
        raise OpenShellLaunchError(
            "Could not configure the Experimentalist OpenShell providers. "
            "Check inference and source-control credentials above."
        )


def _apply_runtime_defaults(runtime_env: dict[str, str]) -> None:
    """Fill safe, process-local defaults needed by the one-command launcher."""
    runtime_env.setdefault("EXPERIMENTALIST_SMART_MODEL_NAME", DEFAULT_SMART_MODEL)
    if not runtime_env.get("NVIDIA_API_KEY") and runtime_env.get("INFERENCE_API_KEY"):
        runtime_env["NVIDIA_API_KEY"] = runtime_env["INFERENCE_API_KEY"]
    if platform.system() == "Darwin":
        runtime_env.setdefault("NEMO_EXPERIMENTALIST_POLICY_MODE", "docker-desktop")


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
    _apply_runtime_defaults(runtime_env)
    managed_bridge = _start_bridge(workspace=workspace, runtime_env=runtime_env)
    try:
        _configure_providers(runtime_env)
        completed = subprocess.run(  # noqa: S603
            [str(script_path), str(workspace), command, *forwarded_args],
            env=runtime_env,
            check=False,
        )
        return completed.returncode
    finally:
        if managed_bridge is not None:
            managed_bridge.stop()
