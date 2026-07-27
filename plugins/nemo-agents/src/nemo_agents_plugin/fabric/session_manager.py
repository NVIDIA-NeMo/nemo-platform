# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle coordination for Platform-managed Fabric runtime sessions."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.environment import ensure_local_workspace_dir
from nemo_agents_plugin.fabric.runtime import FabricInvocationRequest, FabricRuntimeResult, invoke_fabric_runtime
from nemo_agents_plugin.fabric.session_registry import (
    FabricRuntimeSession,
    FabricSessionNotFoundError,
    FabricSessionRegistry,
)
from nemo_agents_plugin.fabric.translator import FabricTranslationError, translate_agent_config

# CI type-checks this plugin via ty extra-paths without installing nemo-agents deps.
from nemo_fabric import Fabric, FabricError  # ty: ignore[unresolved-import]

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT_INVOCATIONS = 8
DEFAULT_IDLE_SESSION_TIMEOUT_SECONDS = 30 * 60
DEFAULT_SESSION_CLEANUP_INTERVAL_SECONDS = 5 * 60


class FabricSessionStartError(RuntimeError):
    """Raised when a Fabric runtime cannot be started for a Platform session."""


class FabricSessionStopError(RuntimeError):
    """Raised when a Fabric runtime cannot be stopped for a Platform session."""


class FabricSessionManager:
    """Create Fabric runtimes lazily from one reusable Platform agent definition."""

    def __init__(
        self,
        agent_config: AgentConfig,
        *,
        base_dir: Path,
        session_registry: FabricSessionRegistry,
        fabric: Any | None = None,
        max_concurrent_invocations: int = DEFAULT_MAX_CONCURRENT_INVOCATIONS,
    ) -> None:
        if max_concurrent_invocations < 0:
            raise ValueError("max_concurrent_invocations must be greater than or equal to zero.")

        self._agent_config = agent_config
        self._base_dir = base_dir
        self._session_registry = session_registry
        self._fabric = fabric
        self._invocation_semaphore = (
            asyncio.Semaphore(max_concurrent_invocations) if max_concurrent_invocations > 0 else None
        )

    async def open_session(self) -> FabricRuntimeSession:
        """Materialize a Fabric config, start its runtime, and register the session."""
        try:
            fabric_config = translate_agent_config(self._agent_config)
        except FabricTranslationError as error:
            raise FabricSessionStartError(f"Fabric config translation failed: {error}") from error

        await asyncio.to_thread(ensure_local_workspace_dir, self._agent_config, self._base_dir)
        fabric = self._fabric or Fabric()
        try:
            runtime = await fabric.start_runtime(fabric_config, base_dir=self._base_dir)
        except FabricError as error:
            raise FabricSessionStartError(f"Fabric runtime startup failed: {error}") from error

        try:
            return await self._session_registry.register(runtime)
        except BaseException:
            # A started runtime must not leak if registration fails or is cancelled.
            try:
                await runtime.stop()
            except FabricError:
                logger.exception("Failed to stop Fabric runtime after session registration failed.")
            raise

    async def resolve_session(self, session_id: str | None) -> FabricRuntimeSession:
        """Open a new session or resolve an existing session by its opaque ID."""
        if session_id is None:
            return await self.open_session()
        return await self._session_registry.get(session_id)

    async def invoke_session(
        self,
        session: FabricRuntimeSession,
        request: FabricInvocationRequest,
    ) -> FabricRuntimeResult:
        """Serialize and invoke one turn on a session's active runtime."""
        async with session.invocation_lock:
            if session.closing:
                raise FabricSessionNotFoundError(f"Fabric session '{session.session_id}' was not found.")
            try:
                if self._invocation_semaphore is None:
                    return await invoke_fabric_runtime(session.runtime, request)
                async with self._invocation_semaphore:
                    return await invoke_fabric_runtime(session.runtime, request)
            finally:
                await self._session_registry.refresh_activity(session)

    async def close_session(self, session_id: str) -> None:
        """Remove a session and stop its runtime after any active turn finishes."""
        session = await self._session_registry.remove(session_id)
        if session is None:
            raise FabricSessionNotFoundError(f"Fabric session '{session_id}' was not found.")

        await self._stop_session(session)

    async def expire_idle_sessions(self, *, idle_timeout_seconds: float) -> int:
        """Stop and remove sessions that have exceeded the idle timeout."""
        expired = await self._session_registry.remove_expired(idle_timeout_seconds=idle_timeout_seconds)
        for session in expired:
            try:
                await self._stop_session(session)
            except FabricSessionStopError:
                logger.exception("Failed to stop expired Fabric session %s.", session.session_id)
        return len(expired)

    async def close_all_sessions(self) -> int:
        """Drain the registry and stop every remaining runtime."""
        sessions = await self._session_registry.drain()

        async def stop_session(session: FabricRuntimeSession) -> None:
            try:
                await self._stop_session(session)
            except FabricSessionStopError:
                logger.exception("Failed to stop Fabric session %s during shutdown.", session.session_id)

        await asyncio.gather(*(stop_session(session) for session in sessions))
        return len(sessions)

    async def _stop_session(self, session: FabricRuntimeSession) -> None:
        """Stop one session after any active invocation releases its lock."""
        async with session.invocation_lock:
            try:
                await session.runtime.stop()
            except FabricError as error:
                raise FabricSessionStopError(f"Fabric runtime shutdown failed: {error}") from error
