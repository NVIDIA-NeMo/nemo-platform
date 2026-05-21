# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AgentDeploymentController — reconciles AgentDeployment entities against the RunnerBackend.

Registered under the ``nemo.controllers`` entry-point group so the platform
runner manages its lifecycle (startup, reconcile loop, graceful shutdown)
without any wiring in :class:`~nemo_agents_plugin.service.AgentsService`.

Every ``interval_seconds`` (driven by :class:`~nemo_platform_plugin.controller.NemoController`)
it queries the Entities Service for ``agent_deployment`` entities and drives
state transitions:

State machine::

    pending   → starting  (backend.create_deployment succeeds)
    starting  → running   (health check passes within timeout)
    starting  → failed    (health check times out or process exits)
    running   → failed    (process exits unexpectedly)
    running   → pending   (process not found in backend, attempting to restart)
    deleting  → (removed) (backend.delete_deployment + entity deleted)
"""

from __future__ import annotations

import logging
import time
from typing import cast

from nemo_agents_plugin.config import ControllerConfig
from nemo_agents_plugin.entities import AgentDeployment
from nemo_agents_plugin.runner.backend import RunnerBackend
from nemo_platform_plugin.controller import NemoController
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError

logger = logging.getLogger(__name__)


class AgentDeploymentController(NemoController):
    """Reconciles ``agent_deployment`` entities against a :class:`RunnerBackend`.

    Extends :class:`~nemo_platform_plugin.controller.NemoController` so the platform
    runner manages its loop, startup, and graceful shutdown automatically.
    Register this class under ``nemo.controllers`` in ``pyproject.toml``; the
    platform will instantiate it and wire it into the thread-based
    ``Loop`` / ``Controller`` framework via ``NemoControllerAdapter``.

    All dependencies (entity client, backend) are initialised in
    :meth:`on_startup` so there is nothing platform-specific in ``__init__``.
    """

    name = "agents-deployment"

    def __init__(self) -> None:
        self._backend: RunnerBackend | None = None
        self._entities: NemoEntitiesClient | None = None
        self._controller_config: ControllerConfig | None = None
        self._starting_since: dict[str, float] = {}
        self._interval_seconds: float = 2.0  # overwritten in on_startup

    # ------------------------------------------------------------------
    # Narrowing properties — raise clearly if accessed before on_startup()
    # ------------------------------------------------------------------

    @property
    def backend(self) -> RunnerBackend:
        if self._backend is None:
            raise RuntimeError("AgentDeploymentController.backend accessed before on_startup()")
        return self._backend

    @property
    def entities(self) -> NemoEntitiesClient:
        if self._entities is None:
            raise RuntimeError("AgentDeploymentController.entities accessed before on_startup()")
        return self._entities

    @property
    def controller_config(self) -> ControllerConfig:
        if self._controller_config is None:
            raise RuntimeError("AgentDeploymentController.controller_config accessed before on_startup()")
        return self._controller_config

    # ------------------------------------------------------------------
    # NemoController interface
    # ------------------------------------------------------------------

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    async def on_startup(self) -> None:
        """Initialise the entity client and runner backend from config."""
        # Imports deferred intentionally: these modules pull in the SDK,
        # entity-store client, and HTTP machinery.  Importing at module level
        # would add ~1s to every `nemo` CLI invocation during plugin discovery,
        # even when the agents controller is never started.  Do not hoist.
        from nemo_agents_plugin.config import AgentsConfig
        from nemo_agents_plugin.runner.registry import RunnerBackendRegistry
        from nemo_platform.resources.entities import AsyncEntitiesResource
        from nmp.common.entities.client import EntityClient as _EntityClient
        from nmp.common.sdk_factory import get_async_platform_sdk

        config = AgentsConfig.get()
        self._interval_seconds = float(config.controller.interval_seconds)
        self._controller_config = config.controller

        # Build a service-principal entity client for the controller background task.
        #
        # We use get_async_platform_sdk() directly (not entity_client.as_service()) because
        # on_startup() runs outside request scope — there is no existing EntityClient to elevate.
        # get_async_platform_sdk(as_service=..., internal=True) applies the same headers that
        # as_service(internal=True) would: X-NMP-Principal-Id: service:agents plus
        # MARK_INTERNAL_REQUEST_HEADERS.  It also wires the shared HTTP client and URL router,
        # which as_service() would inherit from an existing client but we must set up from scratch.
        sdk = get_async_platform_sdk(as_service="agents", internal=True)
        entities_api = AsyncEntitiesResource(sdk)
        self._entities = _EntityClient(entities_api)

        registry = RunnerBackendRegistry(config)
        self._backend = registry.backend

        logger.info("AgentDeploymentController started.")

    async def on_shutdown(self) -> None:
        """Shut down the runner backend."""
        if self._backend is not None:
            await self._backend.shutdown()
        logger.info("AgentDeploymentController shut down.")

    async def list_objects(self) -> list:
        """List all ``agent_deployment`` entities across workspaces."""
        try:
            result = await self.entities.list(AgentDeployment, workspace="-")
            return result.data
        except Exception:
            logger.exception("Failed to list deployments across all workspaces")
            return []

    async def reconcile_one(self, obj: object) -> None:
        """Drive the state machine for a single deployment entity.

        :class:`~nmp.common.entities.client.EntityConflictError` is caught and
        logged as a debug message (optimistic lock; retry next cycle) so it does
        not propagate to the base class's generic error handler.
        """
        dep = cast(AgentDeployment, obj)
        try:
            await self._reconcile_one(dep)
        except NemoEntityConflictError:
            logger.debug("Optimistic lock conflict on '%s' — will retry next cycle.", dep.name)

    # ------------------------------------------------------------------
    # Internal state-machine helpers
    # ------------------------------------------------------------------

    async def _reconcile_one(self, dep: AgentDeployment) -> None:
        if dep.status == "pending":
            await self._start_deployment(dep)
        elif dep.status == "starting":
            await self._check_health(dep)
        elif dep.status == "running":
            await self._verify_running(dep)
        elif dep.status == "deleting":
            await self._delete_deployment(dep)

    async def _start_deployment(self, dep: AgentDeployment) -> None:
        """pending -> starting: allocate port and spawn the agent process."""
        t0 = time.perf_counter()
        port = self.backend.allocate_port()
        try:
            info = await self.backend.create_deployment(
                name=dep.name,
                config=dep.config,
                port=port,
            )
        except Exception as exc:
            logger.exception("Failed to start agent process for deployment '%s'", dep.name)
            dep.status = "failed"
            dep.error = str(exc)
            await self._save(dep)
            return

        spawn_ms = (time.perf_counter() - t0) * 1000
        dep.status = "starting"
        dep.port = info.port
        dep.pid = info.pid
        dep.endpoint = info.endpoint
        dep.error = ""
        self._starting_since[dep.name] = time.monotonic()
        await self._save(dep)
        logger.info(
            "Deployment '%s' spawned (pid=%d, port=%d, spawn=%.0fms, log=%s).",
            dep.name,
            dep.pid,
            dep.port,
            spawn_ms,
            info.log_path or "<none>",
        )

    async def _check_health(self, dep: AgentDeployment) -> None:
        """starting -> running | failed: single-shot health check per reconcile cycle.

        Checks once and returns so the reconcile loop can service other
        deployments promptly.  The ``_starting_since`` timestamp persists
        across cycles so the overall ``health_check_timeout_seconds`` budget
        is enforced across many cycles.
        """
        since = self._starting_since.get(dep.name, time.monotonic())
        timeout = self.controller_config.health_check_timeout_seconds
        elapsed = time.monotonic() - since
        remaining = timeout - elapsed

        if remaining <= 0:
            dep.status = "failed"
            dep.error = f"Health check timed out after {timeout}s."
            await self.backend.delete_deployment(dep.name)
            self._starting_since.pop(dep.name, None)
            await self._save(dep)
            logger.warning("Deployment '%s' health check timed out.", dep.name)
            return

        info = await self.backend.get_deployment_status(dep.name)
        if info is not None and info.status == "failed":
            dep.status = "failed"
            dep.error = info.error or "Process exited unexpectedly during startup."
            self._starting_since.pop(dep.name, None)
            await self._save(dep)
            logger.warning(
                "Deployment '%s' failed during startup: %s (log: %s)",
                dep.name,
                dep.error,
                info.log_path or "<none>",
            )
            return

        healthy = bool(dep.endpoint) and await self.backend.health_check(dep.endpoint)

        if healthy:
            dep.status = "running"
            self._starting_since.pop(dep.name, None)
            await self._save(dep)
            logger.info(
                "Deployment '%s' is running at %s (took %.1fs).",
                dep.name,
                dep.endpoint,
                time.monotonic() - since,
            )
        else:
            logger.debug("Deployment '%s' not healthy yet (%.1fs elapsed).", dep.name, elapsed)

    async def _verify_running(self, dep: AgentDeployment) -> None:
        """mark failed if the process has exited or pending if process is not found to attempt to restart."""
        info = await self.backend.get_deployment_status(dep.name)
        if info is None:
            dep.status = "pending"
            dep.error = "Process not found in backend (attempting to restart)."
            await self._save(dep)
        elif info.status == "failed":
            dep.status = "failed"
            dep.error = info.error or "Process exited unexpectedly."
            await self._save(dep)
            logger.warning("Deployment '%s' failed: %s", dep.name, dep.error)

    async def _delete_deployment(self, dep: AgentDeployment) -> None:
        """deleting → (removed): terminate process and delete entity."""
        await self.backend.delete_deployment(dep.name)
        self._starting_since.pop(dep.name, None)
        try:
            await self.entities.delete(AgentDeployment, name=dep.name, workspace=dep.workspace)
        except Exception:
            logger.exception("Failed to delete deployment entity '%s'", dep.name)
        else:
            logger.info("Deployment '%s' deleted.", dep.name)

    async def _save(self, dep: AgentDeployment) -> None:
        try:
            await self.entities.update(dep)
        except NemoEntityConflictError:
            logger.warning(
                "Optimistic lock conflict saving deployment '%s' — will retry on next reconcile cycle.",
                dep.name,
            )
            raise
        except Exception:
            logger.exception("Failed to update deployment entity '%s'", dep.name)
