# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Named executor registry for deployment backends."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Self

from nemo_deployments_plugin.backends.base import DeploymentBackend
from nemo_deployments_plugin.backends.docker.backend import DockerDeploymentBackend
from nemo_platform import AsyncNeMoPlatform

logger = logging.getLogger(__name__)

BACKEND_CLASSES: dict[str, type[DeploymentBackend]] = {
    "docker": DockerDeploymentBackend,
}


@dataclass(frozen=True)
class ExecutorSpec:
    name: str
    backend: str
    config: dict[str, Any]


class ExecutorNotFoundError(KeyError):
    """Raised when no executor matches the requested name."""


class UnknownBackendTypeError(KeyError):
    """Raised when an executor references an unknown backend type."""


class ExecutorRegistry:
    """Maps executor names to configured DeploymentBackend singletons."""

    def __init__(self, executors: dict[str, DeploymentBackend], *, default_executor: str | None) -> None:
        self._executors = executors
        self._default_executor = default_executor

    @classmethod
    def from_config(
        cls,
        sdk: AsyncNeMoPlatform,
        specs: list[ExecutorSpec],
        *,
        default_executor: str | None = None,
        backend_classes: dict[str, type[DeploymentBackend]] | None = None,
    ) -> Self:
        classes = backend_classes if backend_classes is not None else BACKEND_CLASSES
        if len({spec.name for spec in specs}) != len(specs):
            raise ValueError("Duplicate executor names are not allowed.")
        executors: dict[str, DeploymentBackend] = {}
        try:
            for spec in specs:
                if spec.backend not in classes:
                    raise UnknownBackendTypeError(f"Unknown backend type '{spec.backend}' for executor '{spec.name}'.")
                executors[spec.name] = classes[spec.backend](sdk, spec.config)
            if default_executor and default_executor not in executors:
                raise ExecutorNotFoundError(f"default_executor '{default_executor}' is not registered.")
        except Exception:
            for backend in executors.values():
                backend.shutdown()
            raise
        return cls(executors, default_executor=default_executor)

    @classmethod
    def empty(cls) -> Self:
        """Registry with zero executors — valid at scaffold startup."""
        return cls({}, default_executor=None)

    def resolve(self, name: str | None = None) -> DeploymentBackend:
        executor_name = name or self._default_executor
        if executor_name is None:
            raise ExecutorNotFoundError("No executor specified and no default_executor configured.")
        if executor_name not in self._executors:
            raise ExecutorNotFoundError(f"Executor '{executor_name}' is not registered.")
        return self._executors[executor_name]

    def shutdown_all(self) -> None:
        for name, backend in self._executors.items():
            logger.debug("Shutting down executor '%s'", name)
            backend.shutdown()

    def all_backends(self) -> list[DeploymentBackend]:
        return list(self._executors.values())

    def registered_names(self) -> list[str]:
        return list(self._executors.keys())
