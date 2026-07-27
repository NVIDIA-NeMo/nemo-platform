# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle coordination for Platform-managed Fabric runtime sessions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.runtime import FabricInvocationRequest, FabricRuntimeResult, invoke_fabric_runtime
from nemo_agents_plugin.fabric.session_registry import FabricRuntimeSession, FabricSessionRegistry
from nemo_agents_plugin.fabric.translator import FabricTranslationError, translate_agent_config

# CI type-checks this plugin via ty extra-paths without installing nemo-agents deps.
from nemo_fabric import Fabric, FabricError  # ty: ignore[unresolved-import]

logger = logging.getLogger(__name__)


class FabricSessionStartError(RuntimeError):
    """Raised when a Fabric runtime cannot be started for a Platform session."""


class FabricSessionManager:
    """Create Fabric runtimes lazily from one reusable Platform agent definition."""

    def __init__(
        self,
        agent_config: AgentConfig,
        *,
        base_dir: Path,
        session_registry: FabricSessionRegistry,
        fabric: Any | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._base_dir = base_dir
        self._session_registry = session_registry
        self._fabric = fabric

    async def open_session(self) -> FabricRuntimeSession:
        """Materialize a Fabric config, start its runtime, and register the session."""
        try:
            fabric_config = translate_agent_config(self._agent_config)
        except FabricTranslationError as error:
            raise FabricSessionStartError(f"Fabric config translation failed: {error}") from error

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
            return await invoke_fabric_runtime(session.runtime, request)
