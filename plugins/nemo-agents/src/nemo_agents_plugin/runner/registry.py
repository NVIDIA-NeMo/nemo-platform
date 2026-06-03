# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""RunnerBackendRegistry — factory that instantiates the configured backend."""

from __future__ import annotations

import logging
import threading

from nemo_agents_plugin.config import AgentsConfig
from nemo_agents_plugin.runner.backend import RunnerBackend

logger = logging.getLogger(__name__)


class RunnerBackendRegistry:
    """Instantiates and holds the active :class:`~nemo_agents_plugin.runner.backend.RunnerBackend`.

    The backend type is determined by :attr:`~nemo_agents_plugin.config.AgentsConfig.runner_backend`.
    Currently only ``"in_memory"`` is supported.

    Future backends register here:
    - ``"docker"``  → ``DockerRunnerBackend``
    - ``"k8s"``     → ``K8sRunnerBackend``
    """

    def __init__(self, config: AgentsConfig) -> None:
        backend_type = config.runner_backend
        if backend_type == "in_memory":
            from nemo_agents_plugin.runner.in_memory import InMemoryRunnerBackend

            self._backend: RunnerBackend = InMemoryRunnerBackend(config.controller)
            logger.info(
                "Runner backend: InMemoryRunnerBackend (port range start=%d)", config.controller.port_range_start
            )
        else:
            raise ValueError(f"Unknown runner_backend type '{backend_type}'. Supported values: 'in_memory'.")

    @property
    def backend(self) -> RunnerBackend:
        """The active backend instance."""
        return self._backend


_BACKEND_SINGLETON: RunnerBackend | None = None
_BACKEND_LOCK = threading.Lock()


def set_runner_backend(backend: RunnerBackend) -> None:
    """Publish the process-wide RunnerBackend (called by the controller on startup)."""
    global _BACKEND_SINGLETON  # noqa: PLW0603
    with _BACKEND_LOCK:
        _BACKEND_SINGLETON = backend


def get_runner_backend() -> RunnerBackend:
    """Return the process-wide RunnerBackend (lazy-builds for out-of-process callers)."""
    global _BACKEND_SINGLETON  # noqa: PLW0603
    if _BACKEND_SINGLETON is None:
        # Double-checked lock so concurrent first callers don't build duplicate backends.
        with _BACKEND_LOCK:
            if _BACKEND_SINGLETON is None:
                _BACKEND_SINGLETON = RunnerBackendRegistry(AgentsConfig.get()).backend
    return _BACKEND_SINGLETON


def _reset_runner_backend_for_tests() -> None:
    global _BACKEND_SINGLETON  # noqa: PLW0603
    with _BACKEND_LOCK:
        _BACKEND_SINGLETON = None
