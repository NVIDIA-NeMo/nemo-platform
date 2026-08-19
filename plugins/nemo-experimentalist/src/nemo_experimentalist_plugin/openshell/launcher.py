# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side fail-closed launcher for one prepared Experimentalist run."""

from __future__ import annotations

import ipaddress
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit, urlunsplit

import httpx
from nemo_experimentalist_plugin.harbor_bridge.contracts import BridgeRuntimeConfig
from nemo_experimentalist_plugin.openshell.preparation import PreparedOpenShellRun, SandboxRunManifest

DEFAULT_IMAGE = "local/nmp-experimentalist:local"
DEFAULT_PLATFORM_PORT = 8080
IMAGE_ENV = "NEMO_EXPERIMENTALIST_IMAGE"
PLATFORM_ENV = "NEMO_EXPERIMENTALIST_PLATFORM"
POLICY_MODE_ENV = "NEMO_EXPERIMENTALIST_POLICY_MODE"
RUNTIME_IMAGE_LABEL = "com.nvidia.nemo.experimentalist.openshell-runtime"
RUNTIME_IMAGE_API = "1"
BRIDGE_TOKEN_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN"
BRIDGE_URL_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL"
BRIDGE_PROVIDER_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_PROVIDER"
BRIDGE_BIND_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_BIND"
DEFAULT_BRIDGE_HOST_URL = "http://127.0.0.1:8765"
DEFAULT_BRIDGE_SANDBOX_URL = "http://host.openshell.internal:8765"
LOCAL_PLATFORM_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SANDBOX_HOST_ALIAS = "host.openshell.internal"


class OpenShellLaunchError(RuntimeError):
    """A required runtime component was unavailable before optimization."""


@dataclass(frozen=True, slots=True)
class SandboxPlatformEndpoint:
    """Validated NeMo Platform endpoint exposed to the OpenShell sandbox."""

    url: str
    policy_host: str
    policy_port: int
    terminate_tls: bool


@dataclass
class HarborBridge:
    """Lifecycle owner for a Harbor bridge used by one OpenShell run.

    :meth:`start` either attaches to an explicitly configured, already-running
    bridge or starts a private bridge for the run. In both cases callers can
    unconditionally invoke :meth:`stop`; attached bridges are never stopped.
    """

    endpoint: str
    process: subprocess.Popen[bytes] | None = None
    log_path: Path | None = None
    log_handle: BinaryIO | None = None
    _stopped: bool = False

    @classmethod
    def start(cls, *, prepared: PreparedOpenShellRun, runtime_env: dict[str, str]) -> HarborBridge:
        """Start a private bridge or validate an explicitly configured one."""
        configured_url = runtime_env.get(BRIDGE_URL_ENV, "").strip()
        token = runtime_env.get(BRIDGE_TOKEN_ENV, "").strip()
        bind_host = runtime_env.get(BRIDGE_BIND_ENV, "").strip() or "0.0.0.0"
        host_url = _host_bridge_url(configured_url) if configured_url else _bridge_probe_url(bind_host)
        if configured_url:
            if not token:
                raise OpenShellLaunchError(f"{BRIDGE_TOKEN_ENV} is required with an explicit {BRIDGE_URL_ENV}")
            if not _bridge_ready(host_url):
                raise OpenShellLaunchError(f"Configured Harbor bridge is not ready: {host_url}")
            return cls(endpoint=host_url)
        if _bridge_ready(host_url):
            raise OpenShellLaunchError(
                f"Port 8765 already has a Harbor bridge; configure {BRIDGE_URL_ENV} and {BRIDGE_TOKEN_ENV} "
                "explicitly to reuse it"
            )

        runtime_env[BRIDGE_TOKEN_ENV] = token or secrets.token_urlsafe(32)
        runtime_env[BRIDGE_URL_ENV] = DEFAULT_BRIDGE_SANDBOX_URL
        bridge_root = prepared.root / "host" / "bridge"
        storage_root = bridge_root / "jobs"
        bridge_root.mkdir(parents=True, exist_ok=True)
        manifest = SandboxRunManifest.model_validate_json(prepared.manifest_path.read_text(encoding="utf-8"))
        evaluator_config = manifest.config.outcome_evaluator_config
        standard_attempts = evaluator_config.get("n_attempts", 3)
        standard_concurrency = evaluator_config.get("n_concurrent_trials", os.cpu_count() or 4)
        if not isinstance(standard_attempts, int) or not 1 <= standard_attempts <= 3:
            raise OpenShellLaunchError("OpenShell Harbor n_attempts must be an integer from 1 to 3")
        if not isinstance(standard_concurrency, int) or standard_concurrency < 1:
            raise OpenShellLaunchError("OpenShell Harbor n_concurrent_trials must be a positive integer")
        runtime_config_path = bridge_root / "runtime-config.json"
        runtime_config = BridgeRuntimeConfig(
            host=bind_host,
            port=8765,
            storage_root=storage_root,
            catalog_root=prepared.catalog_root,
            standard_attempts=standard_attempts,
            standard_concurrency=standard_concurrency,
            max_concurrent_dependency_sessions=standard_concurrency,
        )
        try:
            runtime_config_path.write_text(runtime_config.model_dump_json(indent=2) + "\n", encoding="utf-8")
            runtime_config_path.chmod(0o600)
        except OSError as exc:
            raise OpenShellLaunchError(
                f"Could not write Harbor bridge runtime configuration: {runtime_config_path}"
            ) from exc
        log_path = bridge_root / "bridge.log"
        log_handle = log_path.open("ab")
        process = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "nemo_experimentalist_plugin.harbor_bridge.service",
                "--runtime-config",
                str(runtime_config_path),
            ],
            cwd=prepared.root,
            env=runtime_env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        bridge = cls(endpoint=host_url, process=process, log_path=log_path, log_handle=log_handle)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                bridge.stop()
                detail = log_path.read_text(encoding="utf-8", errors="replace").strip()
                raise OpenShellLaunchError(
                    "The Experimentalist Harbor bridge exited before becoming ready" + (f": {detail}" if detail else "")
                )
            if _bridge_ready(host_url):
                return bridge
            time.sleep(0.2)
        bridge.stop()
        raise OpenShellLaunchError(f"The Experimentalist Harbor bridge did not become ready; see {log_path}")

    def stop(self) -> None:
        """Stop the bridge process and close its log; safe to call repeatedly."""
        if self._stopped:
            return
        self._stopped = True
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle is not None:
            self.log_handle.close()


@contextmanager
def _graceful_sigterm() -> Iterator[None]:
    """Turn a launcher SIGTERM into normal cancellation and cleanup.

    SIGKILL remains uncatchable, but the usual ``kill <pid>`` must run the
    launcher's ``finally`` block and give run.sh time to delete its sandbox.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous = signal.getsignal(signal.SIGTERM)

    def interrupt(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _run_sandbox_script(
    script_path: Path,
    sandbox_input: Path,
    experiment_dir: Path,
    policy_path: Path,
    runtime_env: Mapping[str, str],
) -> str:
    """Run the packaged OpenShell CLI wrapper and terminate it on cancellation."""
    process = subprocess.Popen(  # noqa: S603
        [str(script_path), str(sandbox_input), str(experiment_dir), str(policy_path)],
        env=runtime_env,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, _ = process.communicate()
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        raise
    if process.returncode != 0:
        raise OpenShellLaunchError(f"OpenShell Experimentalist exited with status {process.returncode}")
    return stdout.strip()


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


def _normalized_policy_host(hostname: str) -> str:
    """Normalize a URL hostname for an exact OpenShell policy match."""
    try:
        return ipaddress.ip_address(hostname).compressed
    except ValueError:
        try:
            normalized = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise OpenShellLaunchError(f"Invalid NeMo Platform hostname: {hostname!r}") from exc
        if not normalized or any(
            not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
            for label in normalized.rstrip(".").split(".")
        ):
            raise OpenShellLaunchError(f"Invalid NeMo Platform hostname: {hostname!r}")
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-." for character in normalized):
            raise OpenShellLaunchError(f"Invalid NeMo Platform hostname: {hostname!r}")
        return normalized.rstrip(".")


def _sandbox_platform_endpoint(value: str) -> SandboxPlatformEndpoint:
    """Validate and translate a host Platform URL for sandbox access."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise OpenShellLaunchError(f"Invalid NeMo Platform URL: {value}") from exc
    if parsed.scheme not in {"http", "https"} or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise OpenShellLaunchError("The OpenShell policy requires a root HTTP or HTTPS NeMo Platform URL")
    if parsed.username is not None or parsed.password is not None:
        raise OpenShellLaunchError("NeMo Platform URL must not contain user information")
    if parsed.hostname is None:
        raise OpenShellLaunchError("NeMo Platform URL must include a hostname")

    source_host = _normalized_policy_host(parsed.hostname)
    is_local = source_host in LOCAL_PLATFORM_HOSTS
    policy_host = SANDBOX_HOST_ALIAS if is_local else source_host
    if port is not None:
        platform_port = port
    elif is_local:
        platform_port = DEFAULT_PLATFORM_PORT
    else:
        platform_port = 443 if parsed.scheme == "https" else 80
    if not 1 <= platform_port <= 65_535:
        raise OpenShellLaunchError("NeMo Platform URL port must be between 1 and 65535")

    authority_host = f"[{policy_host}]" if ":" in policy_host else policy_host
    sandbox_url = urlunsplit(
        (parsed.scheme, f"{authority_host}:{platform_port}", parsed.path, parsed.query, parsed.fragment)
    )
    return SandboxPlatformEndpoint(
        url=sandbox_url,
        policy_host=policy_host,
        policy_port=platform_port,
        terminate_tls=parsed.scheme == "https",
    )


def _sandbox_platform_url(value: str) -> str:
    """Return the sandbox-visible URL for a validated Platform endpoint."""
    return _sandbox_platform_endpoint(value).url


def _render_runtime_policy(
    prepared: PreparedOpenShellRun,
    runtime_env: Mapping[str, str],
    *,
    platform_endpoint: SandboxPlatformEndpoint,
) -> Path:
    """Render the selected policy with the run's validated Platform endpoint.

    Args:
        prepared: Prepared run whose host directory owns the rendered policy.
        runtime_env: Host environment containing the optional policy mode.
        platform_endpoint: Exact host, port, and TLS behavior allowed from the sandbox.

    Returns:
        Path to the run-specific policy consumed by the OpenShell CLI.

    Raises:
        OpenShellLaunchError: If the policy mode or packaged template is invalid.
    """
    mode = runtime_env.get(POLICY_MODE_ENV, "strict").strip() or "strict"
    policy_names = {
        "strict": "policy.yaml",
        "docker-desktop": "policy.docker-desktop.yaml",
    }
    policy_name = policy_names.get(mode)
    if policy_name is None:
        raise OpenShellLaunchError(f"{POLICY_MODE_ENV} must be strict or docker-desktop")

    template_path = Path(__file__).with_name(policy_name)
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpenShellLaunchError(f"Could not read packaged OpenShell policy: {template_path}") from exc

    host_marker = f"      - host: {SANDBOX_HOST_ALIAS}\n"
    port_marker = f"        port: {DEFAULT_PLATFORM_PORT}\n"
    protocol_marker = "        protocol: rest\n"
    if template.count(host_marker) != 1 or template.count(port_marker) != 1 or template.count(protocol_marker) != 1:
        raise OpenShellLaunchError(f"Packaged OpenShell policy has an unexpected Platform endpoint: {template_path}")

    rendered = template.replace(host_marker, f'      - host: "{platform_endpoint.policy_host}"\n', 1)
    rendered = rendered.replace(port_marker, f"        port: {platform_endpoint.policy_port}\n", 1)
    if platform_endpoint.terminate_tls:
        rendered = rendered.replace(protocol_marker, f"{protocol_marker}        tls: terminate\n", 1)

    policy_dir = prepared.root / "host" / "openshell"
    policy_dir.mkdir(parents=True, exist_ok=True)
    policy_path = policy_dir / "policy.yaml"
    try:
        policy_path.write_text(
            rendered,
            encoding="utf-8",
        )
    except OSError as exc:
        raise OpenShellLaunchError(f"Could not write run-specific OpenShell policy: {policy_path}") from exc
    return policy_path


def _acquire_default_image(
    *,
    docker: str,
    image: str,
    prepared: PreparedOpenShellRun,
    runtime_env: dict[str, str],
) -> None:
    """Ensure that the default local OpenShell image has this runtime API.

    Reuse an existing image only when its runtime compatibility label matches
    :data:`RUNTIME_IMAGE_API`. Otherwise build the default image from this
    checkout for the selected Linux platform. Explicitly configured images are
    intentionally handled by the caller and are not inspected or rebuilt.
    """
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
        [
            docker,
            "buildx",
            "bake",
            "-f",
            "docker-bake.hcl",
            "-f",
            "plugins/nemo-experimentalist/docker-bake.hcl",
            "nmp-experimentalist-docker",
            "--load",
        ],
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


def _bridge_probe_url(bind_host: str) -> str:
    if bind_host == "0.0.0.0":
        return DEFAULT_BRIDGE_HOST_URL
    if bind_host == "::":
        return "http://[::1]:8765"
    authority = f"[{bind_host}]" if ":" in bind_host and not bind_host.startswith("[") else bind_host
    return f"http://{authority}:8765"


def _validate_runtime_settings(runtime_env: Mapping[str, str]) -> None:
    """Fail unless the Platform and trusted Harbor settings were resolved explicitly."""
    missing = [
        name
        for name in (
            "NEMO_DEFAULT_MODEL",
            "NEMO_FAST_MODEL",
            "INFERENCE_API_KEY",
            "INFERENCE_API_BASE",
            "AUT_MODEL_NAME",
        )
        if not runtime_env.get(name)
    ]
    if missing:
        raise OpenShellLaunchError("Missing required OpenShell runtime settings: " + ", ".join(missing))


def _configure_providers(prepared: PreparedOpenShellRun, runtime_env: dict[str, str]) -> None:
    script_path = Path(__file__).with_name("configure-providers.sh")
    if not script_path.is_file():
        raise OpenShellLaunchError(f"Packaged provider setup is missing: {script_path}")
    runtime_env["NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR"] = str(prepared.root / "host" / "provider-profiles")
    provider_env = {
        name: value
        for name, value in runtime_env.items()
        if name in {"PATH", "HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"}
    }
    provider_env.update(
        {
            BRIDGE_TOKEN_ENV: runtime_env[BRIDGE_TOKEN_ENV],
            BRIDGE_PROVIDER_ENV: runtime_env[BRIDGE_PROVIDER_ENV],
            "NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR": runtime_env["NEMO_EXPERIMENTALIST_PROVIDER_PROFILE_DIR"],
        }
    )
    completed = subprocess.run([str(script_path)], env=provider_env, check=False)  # noqa: S603
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
        raise OpenShellLaunchError(
            "OpenShell is required for `nemo agents experimentalist run`, but its CLI is not on PATH"
        )
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
    sandbox_platform_endpoint = _sandbox_platform_endpoint(platform_url)
    runtime_env["NMP_BASE_URL"] = sandbox_platform_endpoint.url
    policy_path = _render_runtime_policy(
        prepared,
        runtime_env,
        platform_endpoint=sandbox_platform_endpoint,
    )
    runtime_env["NEMO_EXPERIMENTALIST_OUTPUT_DIR"] = str(experiment_dir.expanduser().resolve())
    runtime_env.setdefault(BRIDGE_PROVIDER_ENV, f"nemo-exp-bridge-{secrets.token_hex(4)}")
    _validate_runtime_settings(runtime_env)
    # Cover provider setup as well as the sandbox process. A SIGTERM at either
    # point must release the sandbox, provider, and bridge.
    with _graceful_sigterm():
        bridge = HarborBridge.start(prepared=prepared, runtime_env=runtime_env)
        providers_attempted = False
        run_completed = False
        try:
            providers_attempted = True
            _configure_providers(prepared, runtime_env)
            script_path = Path(__file__).with_name("run.sh")
            output = _run_sandbox_script(
                script_path,
                prepared.sandbox_input,
                experiment_dir.expanduser().resolve(),
                policy_path,
                runtime_env,
            )
            run_completed = True
            return output
        finally:
            provider_deleted = not providers_attempted or _delete_bridge_provider(openshell, runtime_env)
            bridge.stop()
            if not provider_deleted:
                message = f"Could not delete ephemeral OpenShell provider {runtime_env[BRIDGE_PROVIDER_ENV]!r}"
                if run_completed:
                    raise OpenShellLaunchError(message)
                print(f"WARNING: {message}", file=sys.stderr)
