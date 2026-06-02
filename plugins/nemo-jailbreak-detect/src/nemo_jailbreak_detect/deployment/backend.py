# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployment backends for the jailbreak-detection model server.

The controller talks to the model server through a small backend interface so
the same reconcile loop drives different runtimes. ``DockerBackend`` runs the
server as a local container; ``JobsBackend`` is the extension point for running
it on the platform Jobs/Executor system (k8s, slurm). Both produce a
:class:`DeploymentResult` carrying the backend-specific handle and the resolved
endpoint URL.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from dataclasses import dataclass
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeploymentSpec:
    """Everything a backend needs to launch one model server."""

    name: str
    workspace: str
    image: str
    device: str
    port: int
    model_cache_dir: str


@dataclass(frozen=True)
class DeploymentResult:
    """Outcome of an ensure-started call."""

    handle: str
    endpoint_url: str


class DeploymentBackend(Protocol):
    """Lifecycle operations the controller drives. Implementations must be idempotent."""

    async def ensure_started(self, spec: DeploymentSpec) -> DeploymentResult: ...

    async def is_ready(self, endpoint_url: str, timeout: float) -> bool: ...

    async def stop(self, handle: str) -> None: ...


async def _run(*args: str) -> tuple[int, str, str]:
    """Run a subprocess, returning (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        # e.g. the `docker` binary is not installed on the controller host.
        raise RuntimeError(f"Command not found: {args[0]!r}. Is it installed and on PATH?") from exc
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode().strip(), stderr.decode().strip()


async def probe_ready(endpoint_url: str, timeout: float) -> bool:
    """Shared readiness probe against the server's ``/v1/health/ready``."""
    url = endpoint_url.rstrip("/") + "/v1/health/ready"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except httpx.HTTPError as exc:
        logger.debug("Readiness probe failed for %s: %s", url, exc)
        return False


class DockerBackend:
    """Manage the model server as a local Docker container via the docker CLI.

    Uses ``docker`` over the CLI (no docker-py dependency). Container names are
    scoped by ``workspace`` + deployment name so operations are idempotent and
    deployments in different workspaces don't collide.

    The endpoint is resolved against ``host`` (default ``localhost``), which
    assumes the controller shares the host's network namespace with the
    container — true for local/dev runs, not for k8s. Cross-host/k8s deployment
    is the job of :class:`JobsBackend`.

    Note: each deployment must use a distinct host ``port``; a collision surfaces
    as a loud ``docker run`` bind error that marks the deployment failed.
    """

    def __init__(self, host: str = "localhost") -> None:
        self._host = host

    @staticmethod
    def _container_name(workspace: str, name: str) -> str:
        return f"nemo-jailbreak-detect-{workspace}-{name}"

    async def ensure_started(self, spec: DeploymentSpec) -> DeploymentResult:
        container = self._container_name(spec.workspace, spec.name)
        endpoint_url = f"http://{self._host}:{spec.port}"

        # Already running? Treat as success (idempotent reconcile).
        code, stdout, _ = await _run(
            "docker", "ps", "--filter", f"name=^{container}$", "--filter", "status=running", "--format", "{{.ID}}"
        )
        if code == 0 and stdout:
            return DeploymentResult(handle=stdout.splitlines()[0], endpoint_url=endpoint_url)

        # Remove any stale (exited) container with the same name before starting.
        await _run("docker", "rm", "-f", container)

        run_args = [
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "-e",
            f"JAILBREAK_CHECK_DEVICE={spec.device}",
            "-v",
            f"{spec.model_cache_dir}:/opt/nim/.cache/",
            "-p",
            f"{spec.port}:8000",
        ]
        if spec.device.startswith("cuda"):
            run_args += ["--gpus", "all", "--runtime", "nvidia", "--shm-size", "64GB"]
        run_args.append(spec.image)

        code, stdout, stderr = await _run(*run_args)
        if code != 0:
            raise RuntimeError(f"docker run failed: {stderr or stdout}\n  cmd: {shlex.join(run_args)}")

        return DeploymentResult(handle=stdout.splitlines()[0], endpoint_url=endpoint_url)

    async def is_ready(self, endpoint_url: str, timeout: float) -> bool:
        return await probe_ready(endpoint_url, timeout)

    async def stop(self, handle: str) -> None:
        # handle is the container id; remove forcefully and idempotently.
        await _run("docker", "rm", "-f", handle)


class JobsBackend:
    """Deployment via the platform Jobs/Executor system (k8s/slurm).

    Not yet implemented. Entities and the controller are backend-agnostic, so
    adding it is additive: implement these three methods against the Jobs SDK
    (submit a service job, resolve its inference-gateway URL, cancel it) without
    touching the reconcile loop.
    """

    async def ensure_started(self, spec: DeploymentSpec) -> DeploymentResult:
        raise NotImplementedError(
            "JobsBackend is not implemented yet. Use backend='docker', or implement "
            "submission against the platform Jobs/Executor system here."
        )

    async def is_ready(self, endpoint_url: str, timeout: float) -> bool:
        return await probe_ready(endpoint_url, timeout)

    async def stop(self, handle: str) -> None:
        raise NotImplementedError("JobsBackend.stop is not implemented yet.")


def get_backend(kind: str) -> DeploymentBackend:
    """Resolve a backend by kind. Unknown kinds fail loudly rather than defaulting."""
    if kind == "docker":
        return DockerBackend()
    if kind == "jobs":
        return JobsBackend()
    raise ValueError(f"Unknown deployment backend: {kind!r}")
