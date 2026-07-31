# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side fail-closed launcher for one prepared Experimentalist run."""

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
from typing import BinaryIO
from urllib.parse import urlsplit, urlunsplit

import httpx
from nemo_experimentalist_plugin.openshell.preparation import PreparedOpenShellRun

DEFAULT_IMAGE = "local/nmp-experimentalist:local"
IMAGE_ENV = "NEMO_EXPERIMENTALIST_IMAGE"
PLATFORM_ENV = "NEMO_EXPERIMENTALIST_PLATFORM"
RUNTIME_IMAGE_LABEL = "com.nvidia.nemo.experimentalist.openshell-runtime"
RUNTIME_IMAGE_API = "1"
BRIDGE_TOKEN_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN"
BRIDGE_URL_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL"
BRIDGE_PROVIDER_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_PROVIDER"
DEFAULT_BRIDGE_HOST_URL = "http://127.0.0.1:8765"
DEFAULT_BRIDGE_SANDBOX_URL = "http://host.openshell.internal:8765"
DEFAULT_SMART_MODEL = "openai/openai/openai/gpt-5.5"


class OpenShellLaunchError(RuntimeError):
    """A required runtime component was unavailable before optimization."""


@dataclass
class _ManagedBridge:
    process: subprocess.Popen[bytes]
    log_path: Path
    log_handle: BinaryIO

    def stop(self) -> None:
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


def _sandbox_platform_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise OpenShellLaunchError(f"Invalid NeMo Platform URL: {value}") from exc
    if parsed.scheme != "http" or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise OpenShellLaunchError("The prototype OpenShell policy requires the root HTTP NeMo Platform URL")
    if parsed.username is not None or parsed.password is not None:
        raise OpenShellLaunchError("NeMo Platform URL must not contain user information")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise OpenShellLaunchError("The prototype OpenShell policy supports only a host-local NeMo Platform URL")
    if port not in (None, 8080):
        raise OpenShellLaunchError("The prototype OpenShell policy supports NeMo Platform only on port 8080")
    return urlunsplit((parsed.scheme, "host.openshell.internal:8080", parsed.path, parsed.query, parsed.fragment))


def _acquire_default_image(
    *,
    docker: str,
    image: str,
    prepared: PreparedOpenShellRun,
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
    repo_root = _find_repo_root(prepared.root, Path(__file__).resolve())
    if repo_root is None:
        raise OpenShellLaunchError(
            f"A compatible Experimentalist image {image!r} is not available. "
            f"Set {IMAGE_ENV} to a published image or run from a nemo-platform checkout."
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
        raise OpenShellLaunchError(f"Could not build {image!r} for {selected_platform}")


def _bridge_ready(url: str) -> bool:
    try:
        return httpx.get(f"{url.rstrip('/')}/health/ready", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


def _host_bridge_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.hostname != "host.openshell.internal":
        return value
    port_suffix = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit((parsed.scheme, f"127.0.0.1{port_suffix}", parsed.path, parsed.query, parsed.fragment))


def _start_bridge(
    *,
    prepared: PreparedOpenShellRun,
    runtime_env: dict[str, str],
) -> _ManagedBridge | None:
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
        raise OpenShellLaunchError(
            f"Port 8765 already has a Harbor bridge; configure {BRIDGE_URL_ENV} and {BRIDGE_TOKEN_ENV} "
            "explicitly to reuse it"
        )

    token = token or secrets.token_urlsafe(32)
    runtime_env[BRIDGE_TOKEN_ENV] = token
    runtime_env[BRIDGE_URL_ENV] = DEFAULT_BRIDGE_SANDBOX_URL
    bridge_root = prepared.root / "host" / "bridge"
    storage_root = bridge_root / "jobs"
    bridge_root.mkdir(parents=True, exist_ok=True)
    log_path = bridge_root / "bridge.log"
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
            "--catalog-root",
            str(prepared.catalog_root),
        ],
        cwd=prepared.root,
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
    raise OpenShellLaunchError(f"The Experimentalist Harbor bridge did not become ready; see {log_path}")


def _apply_runtime_defaults(runtime_env: dict[str, str]) -> None:
    runtime_env.setdefault("EXPERIMENTALIST_SMART_MODEL_NAME", DEFAULT_SMART_MODEL)
    if not runtime_env.get("INFERENCE_API_KEY") and runtime_env.get("NVIDIA_API_KEY"):
        runtime_env["INFERENCE_API_KEY"] = runtime_env["NVIDIA_API_KEY"]
    runtime_env.setdefault("INFERENCE_API_BASE", "https://inference-api.nvidia.com/v1")
    if not runtime_env.get("AUT_MODEL_NAME"):
        configured_model = runtime_env.get("NEMO_EXPERIMENTALIST_AUT_MODEL_NAME")
        if configured_model:
            runtime_env["AUT_MODEL_NAME"] = configured_model
    missing = [
        name for name in ("INFERENCE_API_KEY", "INFERENCE_API_BASE", "AUT_MODEL_NAME") if not runtime_env.get(name)
    ]
    if missing:
        raise OpenShellLaunchError("Missing trusted candidate inference settings: " + ", ".join(missing))
    if not runtime_env.get("NVIDIA_API_KEY"):
        runtime_env["NVIDIA_API_KEY"] = runtime_env["INFERENCE_API_KEY"]
    if platform.system() == "Darwin":
        runtime_env.setdefault("NEMO_EXPERIMENTALIST_POLICY_MODE", "docker-desktop")


def _configure_providers(prepared: PreparedOpenShellRun, runtime_env: dict[str, str]) -> None:
    script_path = Path(__file__).with_name("configure-providers.sh")
    if not script_path.is_file():
        raise OpenShellLaunchError(f"Packaged provider setup is missing: {script_path}")
    runtime_env["NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR"] = str(prepared.root / "host" / "provider-profiles")
    completed = subprocess.run([str(script_path)], env=runtime_env, check=False)  # noqa: S603
    if completed.returncode != 0:
        raise OpenShellLaunchError("Could not configure the Experimentalist OpenShell providers")


def _delete_bridge_provider(openshell: str, runtime_env: Mapping[str, str]) -> bool:
    provider = runtime_env[BRIDGE_PROVIDER_ENV]
    completed = subprocess.run(  # noqa: S603
        [openshell, "provider", "delete", provider],
        env=runtime_env,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def launch_openshell_run(
    prepared: PreparedOpenShellRun,
    *,
    experiment_dir: Path,
    platform_url: str,
    env: Mapping[str, str] | None = None,
) -> str:
    """Run the prepared manifest in OpenShell; never call Experimentalist locally."""
    runtime_env = dict(os.environ if env is None else env)
    openshell = shutil.which("openshell", path=runtime_env.get("PATH"))
    if openshell is None:
        raise OpenShellLaunchError("OpenShell is required for `nemo experimentalist run`, but its CLI is not on PATH")
    image = runtime_env.get(IMAGE_ENV, "").strip() or DEFAULT_IMAGE
    runtime_env[IMAGE_ENV] = image
    if image == DEFAULT_IMAGE:
        docker = shutil.which("docker", path=runtime_env.get("PATH"))
        if docker is None:
            raise OpenShellLaunchError(
                f"Default image {image!r} requires Docker for local discovery/build; set {IMAGE_ENV} "
                "to an image available to the OpenShell gateway"
            )
        _acquire_default_image(
            docker=docker,
            image=image,
            prepared=prepared,
            runtime_env=runtime_env,
        )
    runtime_env["NMP_BASE_URL"] = _sandbox_platform_url(platform_url)
    runtime_env["NEMO_EXPERIMENTALIST_OUTPUT_DIR"] = str(experiment_dir.expanduser().resolve())
    runtime_env.setdefault(BRIDGE_PROVIDER_ENV, f"nemo-exp-bridge-{secrets.token_hex(4)}")
    _apply_runtime_defaults(runtime_env)
    managed_bridge = _start_bridge(prepared=prepared, runtime_env=runtime_env)
    providers_configured = False
    run_completed = False
    try:
        _configure_providers(prepared, runtime_env)
        providers_configured = True
        script_path = Path(__file__).with_name("run.sh")
        completed = subprocess.run(  # noqa: S603
            [str(script_path), str(prepared.sandbox_input), str(experiment_dir.expanduser().resolve())],
            env=runtime_env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
        )
        if completed.returncode != 0:
            raise OpenShellLaunchError(f"OpenShell Experimentalist exited with status {completed.returncode}")
        run_completed = True
        return completed.stdout.strip()
    finally:
        provider_deleted = not providers_configured or _delete_bridge_provider(openshell, runtime_env)
        if managed_bridge is not None:
            managed_bridge.stop()
        if not provider_deleted:
            message = f"Could not delete ephemeral OpenShell provider {runtime_env[BRIDGE_PROVIDER_ENV]!r}"
            if run_completed:
                raise OpenShellLaunchError(message)
            print(f"WARNING: {message}", file=sys.stderr)
