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
from typing import Any

from nemo_agents_plugin.entities import DeploymentStatus


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
    async def create_deployment(self, name: str, config: dict[str, Any], port: int) -> DeploymentInfo:
        """Start an agent process from a NAT workflow config dict.

        Args:
            name: Deployment name (used for process tracking).
            config: NAT workflow config with IGW URL already injected.
            port: Port the agent process should listen on.

        Returns:
            :class:`DeploymentInfo` with ``status="starting"`` and ``pid`` populated.
        """
        ...

    @abstractmethod
    async def get_deployment_status(self, name: str) -> DeploymentInfo | None:
        """Return the current runtime state of a deployment, or ``None`` if unknown."""
        ...

    @abstractmethod
    async def delete_deployment(self, name: str) -> bool:
        """Stop and clean up a deployment.

        Returns:
            ``True`` if found and terminated, ``False`` if already cleaned up.
        """
        ...

    @abstractmethod
    async def list_deployments(self) -> list[DeploymentInfo]:
        """Return a snapshot of all deployments managed by this backend."""
        ...

    @abstractmethod
    async def health_check(self, endpoint: str) -> bool:
        """Return ``True`` if the agent at *endpoint* passes ``GET /health``."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Terminate all managed processes and release resources.

        Called during service shutdown.  Must be idempotent.
        """
        ...
