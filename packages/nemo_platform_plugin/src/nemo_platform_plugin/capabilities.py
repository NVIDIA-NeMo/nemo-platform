# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared backend capability probes for NeMo Platform.

Runtime (``platform.runtime``) describes *where the platform process runs*.
Capability probes answer *which backends can run jobs/deployments right now*.

This module owns the Docker probe used by jobs, deployments, setup, and
customization. GPU and Kubernetes helpers are stubs for a future capability
registry (AIRCORE-972); they must not import ``nmp_common``.

Caching
-------
Results are memoized per Docker endpoint for long-lived server processes.
CLI / preflight / tests that re-check after the user starts Docker must call
:func:`reset_capability_cache` (or pass ``use_cache=False``) so a prior miss
does not stick for the process lifetime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

logger = logging.getLogger(__name__)

_DOCKER_PROBE_TIMEOUT_SECONDS = 5


class Capability(str, Enum):
    """Named platform backend capabilities."""

    DOCKER = "docker"
    GPU = "gpu"
    KUBERNETES = "kubernetes"


class CapabilityUnavailableError(RuntimeError):
    """A required backend capability is unavailable.

    Raised when an optional packaging extra is missing or a runtime substrate
    (e.g. Docker daemon/socket) is unreachable. Registries may soft-skip
    optional backends that raise this, while still fail-closing when a
    configured default still names the unavailable backend.
    """


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a capability probe."""

    available: bool
    detail: str | None = None


class CapabilityProbe(Protocol):
    """Pluggable capability probe (AIRCORE-972 extension point)."""

    def probe(self) -> ProbeResult: ...


# Cache keyed by docker host (None → default DOCKER_HOST / from_env).
_docker_probe_cache: dict[str | None, ProbeResult] = {}


def reset_capability_cache() -> None:
    """Clear memoized probe results.

    Call from CLI retry paths (``nemo setup``, quickstart preflight) and from
    test fixtures so a prior unavailable verdict does not pin the process.
    """
    _docker_probe_cache.clear()


def probe_docker(
    *,
    docker_host: str | None = None,
    use_cache: bool = True,
) -> ProbeResult:
    """Probe Docker daemon reachability with a short timeout.

    Args:
        docker_host: Optional Docker API URL override (same meaning as
            ``DOCKER_HOST`` / deployments ``docker_host``). ``None`` uses the
            environment default via ``docker.from_env``.
        use_cache: When True (default), reuse a prior result for this host key.
            Pass False for CLI retry UX after the user starts Docker.
    """
    cache_key = docker_host
    if use_cache and cache_key in _docker_probe_cache:
        return _docker_probe_cache[cache_key]

    result = _probe_docker_uncached(docker_host=docker_host)
    if use_cache:
        _docker_probe_cache[cache_key] = result
    return result


def _probe_docker_uncached(*, docker_host: str | None) -> ProbeResult:
    try:
        from docker.errors import DockerException
        from requests.exceptions import ConnectionError as RequestsConnectionError
        from requests.exceptions import Timeout as RequestsTimeout

        import docker
    except ImportError as exc:
        detail = f"Docker Python package is not installed ({exc})"
        logger.debug(detail)
        return ProbeResult(available=False, detail=detail)

    client = None
    try:
        # Prefer from_env for the default host so DOCKER_* env vars apply; when an
        # explicit host is set, DockerClient(base_url=...) matches deployments.
        if docker_host:
            client = docker.DockerClient(base_url=docker_host, timeout=_DOCKER_PROBE_TIMEOUT_SECONDS)
        else:
            client = docker.from_env(timeout=_DOCKER_PROBE_TIMEOUT_SECONDS)
        client.ping()
        return ProbeResult(available=True, detail=None)
    except (DockerException, RequestsConnectionError, RequestsTimeout, OSError) as exc:
        detail = f"Docker daemon unreachable ({exc})"
        logger.debug(detail)
        return ProbeResult(available=False, detail=detail)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 — best-effort close
                pass


def require_docker(*, docker_host: str | None = None, use_cache: bool = True) -> None:
    """Raise :class:`CapabilityUnavailableError` when Docker is not available."""
    result = probe_docker(docker_host=docker_host, use_cache=use_cache)
    if not result.available:
        raise CapabilityUnavailableError(result.detail or "Docker daemon is unavailable")


def probe_gpu() -> ProbeResult:
    """GPU capability stub — implementation deferred (do not import nmp_common)."""
    return ProbeResult(
        available=False,
        detail="GPU capability probe is not implemented in nemo_platform_plugin (AIRCORE-972)",
    )


def probe_kubernetes() -> ProbeResult:
    """Kubernetes reachability stub — implementation deferred to AIRCORE-972."""
    return ProbeResult(
        available=False,
        detail="Kubernetes capability probe is not implemented yet (AIRCORE-972)",
    )
