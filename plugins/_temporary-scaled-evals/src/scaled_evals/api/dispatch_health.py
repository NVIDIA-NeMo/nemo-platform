# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Informational readiness probes for compose dispatch runtimes (tier 3).

These checks surface gym / sandbox_k8s wiring in ``GET /v1/readyz`` without
failing the control plane when a backend is disabled or misconfigured.
"""

from __future__ import annotations

from pathlib import Path

from scaled_evals.api.settings import settings


class DispatchHealthError(RuntimeError):
    """A dispatch probe failed (informational — does not degrade readyz)."""


def _gym_dispatch_enabled() -> bool:
    return (
        settings.gym_sandbox_daytona_enabled or settings.gym_sandbox_opensandbox_enabled or settings.gym_daytona_enabled
    )


def _configured_status(missing: list[str]) -> str:
    if missing:
        return f"fail: missing {', '.join(missing)}"
    return "ok"


# Every `GET /v1/readyz` runs these probes, so each client is closed rather than left for
# the collector: docker.from_env() opens a requests.Session, and the SDK's own client is not
# a context manager. The timeout is well under the SDK's 60s default so an unresponsive
# daemon delays readiness briefly instead of holding the request open.
_DOCKER_PROBE_TIMEOUT_SECONDS = 5


def _check_docker_daemon() -> None:
    from contextlib import closing

    from docker.errors import DockerException

    import docker

    try:
        with closing(docker.from_env(timeout=_DOCKER_PROBE_TIMEOUT_SECONDS)) as client:
            client.ping()
    except DockerException as exc:
        raise DispatchHealthError(str(exc)) from exc


def _check_docker_image(image: str) -> None:
    from contextlib import closing

    from docker.errors import DockerException, ImageNotFound

    import docker

    try:
        with closing(docker.from_env(timeout=_DOCKER_PROBE_TIMEOUT_SECONDS)) as client:
            client.images.get(image)
    except ImageNotFound as exc:
        raise DispatchHealthError(f"image not found: {image}") from exc
    except DockerException as exc:
        raise DispatchHealthError(str(exc)) from exc


_COMPOSE_KUBE_MOUNT = Path("/root/.kube")


def _check_kubeconfig_available() -> None:
    """Verify kubeconfig is reachable from the API process.

    In compose the host ``~/.kube`` is bind-mounted at ``/root/.kube``; checking
    the host path from inside the API container fails even when dispatch works.
    """
    for kube_dir in (_COMPOSE_KUBE_MOUNT,):
        try:
            found = kube_dir.is_dir() and list(kube_dir.glob("config*"))
        except OSError:
            found = False
        if found:
            return

    host = settings.kube_config_dir_host or settings.kube_config_dir
    if not host:
        raise DispatchHealthError("KUBE_CONFIG_DIR_HOST unset")
    kube_dir = Path(host).expanduser()
    if not kube_dir.is_dir():
        raise DispatchHealthError("kubeconfig directory missing")
    if not list(kube_dir.glob("config*")):
        raise DispatchHealthError("no kubeconfig file in directory")


def _check_existing_path(value: str | None, label: str, *, directory: bool = False) -> None:
    if not value:
        raise DispatchHealthError(f"{label} unset")
    path = Path(value).expanduser()
    if directory:
        if not path.is_dir():
            raise DispatchHealthError(f"{label} directory missing: {value}")
    elif not path.is_file():
        raise DispatchHealthError(f"{label} file missing: {value}")


def check_gym_dispatch() -> str:
    """Return readyz status token for gym compose dispatch."""
    if not _gym_dispatch_enabled():
        return "skipped: disabled"
    if settings.dispatch_health_mode == "configured":
        missing = []
        if settings.gym_daytona_enabled and not settings.gym_daytona_env_file:
            missing.append("GYM_DAYTONA_ENV_FILE")
        if settings.gym_sandbox_daytona_enabled and not settings.gym_sandbox_daytona_env_file:
            missing.append("GYM_SANDBOX_DAYTONA_ENV_FILE")
        if settings.gym_sandbox_opensandbox_enabled and not settings.gym_sandbox_opensandbox_env_file:
            missing.append("GYM_SANDBOX_OPENSANDBOX_ENV_FILE")
        if settings.gym_runner_mode == "process":
            if not settings.gym_runner_image:
                missing.append("GYM_RUNNER_IMAGE")
            if not settings.gym_runner_image_digest:
                missing.append("GYM_RUNNER_IMAGE_DIGEST")
            if not settings.gym_source_revision:
                missing.append("GYM_SOURCE_REVISION")
        return _configured_status(missing)
    if not settings.gym_runner_image:
        return "skipped: no GYM_RUNNER_IMAGE"
    try:
        _check_docker_daemon()
        _check_docker_image(settings.gym_runner_image)
    except DispatchHealthError as exc:
        return f"fail: {exc}"
    return "ok"


def check_sandbox_k8s_dispatch() -> str:
    """Return readyz status token for sandbox_k8s compose dispatch."""
    if not settings.sandbox_k8s_enabled:
        return "skipped: disabled"
    if settings.dispatch_health_mode == "configured":
        missing = []
        if not settings.sandbox_k8s_config_path:
            missing.append("SANDBOX_K8S_CONFIG_PATH")
        if not settings.sandbox_k8s_env_file:
            missing.append("SANDBOX_K8S_ENV_FILE")
        if not settings.sandbox_k8s_jobs_dir:
            missing.append("SANDBOX_K8S_JOBS_DIR")
        return _configured_status(missing)
    try:
        _check_existing_path(settings.sandbox_k8s_config_path, "SANDBOX_K8S_CONFIG_PATH")
        _check_existing_path(settings.sandbox_k8s_env_file, "SANDBOX_K8S_ENV_FILE")
        if not settings.sandbox_k8s_jobs_dir:
            raise DispatchHealthError("SANDBOX_K8S_JOBS_DIR unset")
        if settings.harbor_runner_image:
            _check_docker_daemon()
            _check_docker_image(settings.harbor_runner_image)
        else:
            _check_existing_path(settings.harbor_dir, "HARBOR_DIR", directory=True)
        _check_kubeconfig_available()
    except DispatchHealthError as exc:
        return f"fail: {exc}"
    return "ok"
