# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RunnerBackend abstraction — manages the lifecycle of agent runtime processes.

Implementations:
- :class:`~nemo_agents_plugin.runner.in_memory.InMemoryRunnerBackend` — spawns
  ``nat serve`` subprocesses (initial implementation).

Future backends (interface designed to support these):
- ``DockerRunnerBackend`` — runs agent containers via the Docker API.
- ``K8sRunnerBackend`` — creates K8s Pods/Deployments for agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from nemo_agents_plugin.entities import DeploymentStatus


@dataclass(frozen=True)
class LocalLog:
    """Log file lives on this host."""

    path: Path
    kind: Literal["local"] = "local"


@dataclass(frozen=True)
class NotYetAvailable:
    """Deployment exists; runtime hasn't produced log output yet."""

    kind: Literal["not_yet_available"] = "not_yet_available"


@dataclass(frozen=True)
class ExternalLog:
    """Logs fetched via a backend-specific channel (``docker logs``, ``kubectl logs``, ...)."""

    kind: Literal["external"] = "external"
    hint: str = ""


LogLocation = LocalLog | NotYetAvailable | ExternalLog


@dataclass
class DeploymentInfo:
    """Runtime snapshot of a deployment managed by the backend.

    This is the backend's in-memory view, distinct from the ``AgentDeployment``
    entity in the store.  The controller reads this to update the entity.
    """

    name: str
    status: DeploymentStatus = "pending"
    endpoint: str = ""
    """HTTP endpoint of the process, e.g. ``http://localhost:9001``."""
    port: int = 0
    pid: int = 0
    error: str = ""
    log_path: str = ""
    """Absolute path to the subprocess log file (empty if not applicable)."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Backend-specific metadata (e.g. container ID for Docker)."""


class RunnerBackend(ABC):
    """Abstract base class for managing agent runtime processes.

    All async methods are called from the asyncio reconcile loop.
    Blocking operations must use ``asyncio.to_thread`` internally.
    """

    def allocate_port(self) -> int:
        """Return the next port to use for a new deployment.

        Backends that manage port allocation override this.  The default
        returns 0, meaning the backend handles port allocation internally
        (e.g. Docker, Kubernetes).
        """
        return 0

    @abstractmethod
    async def create_deployment(self, workspace: str, name: str, config: dict[str, Any], port: int) -> DeploymentInfo:
        """Start the agent process; returns status="starting"."""
        ...

    @abstractmethod
    async def get_deployment_status(self, workspace: str, name: str) -> DeploymentInfo | None:
        """Return the current runtime state of a deployment, or ``None`` if unknown."""
        ...

    @abstractmethod
    async def delete_deployment(self, workspace: str, name: str) -> bool:
        """Stop + clean up; True if found, False if already gone."""
        ...

    @abstractmethod
    async def list_deployments(self, workspace: str | None = None) -> list[DeploymentInfo]:
        """Snapshot of deployments; ``workspace=None`` returns every workspace."""
        ...

    @abstractmethod
    async def health_check(self, endpoint: str) -> bool:
        """Return ``True`` if the agent at *endpoint* passes ``GET /health``."""
        ...

    def get_log_location(self, workspace: str, name: str) -> "LogLocation":
        """Where to read logs for (workspace, name). Default: NotYetAvailable."""
        del workspace, name
        return NotYetAvailable()

    @abstractmethod
    async def shutdown(self) -> None:
        """Terminate all managed processes and release resources.

        Called during service shutdown.  Must be idempotent.
        """
        ...
