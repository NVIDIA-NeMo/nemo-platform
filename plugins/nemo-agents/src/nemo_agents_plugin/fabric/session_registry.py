# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Process-local logical session registry for Fabric runtimes."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemo_fabric import Runtime


@dataclass(slots=True)
class FabricRuntimeSession:
    """Platform session bound to one stateful Fabric runtime."""

    session_id: str
    runtime: Runtime
    created_at: float
    last_accessed_at: float


class FabricSessionNotFoundError(LookupError):
    """Raised when a logical Fabric session is not registered."""


class FabricSessionAlreadyExistsError(ValueError):
    """Raised when a logical Fabric session ID is registered twice."""


class FabricSessionRegistry:
    """Maintain the process-local mapping from Platform sessions to runtimes."""

    def __init__(self) -> None:
        self._sessions: dict[str, FabricRuntimeSession] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        runtime: Runtime,
        *,
        session_id: str | None = None,
    ) -> FabricRuntimeSession:
        """Bind a new opaque Platform session ID to a Fabric runtime."""
        resolved_session_id = session_id or str(uuid.uuid4())
        now = time.monotonic()
        session = FabricRuntimeSession(
            session_id=resolved_session_id,
            runtime=runtime,
            created_at=now,
            last_accessed_at=now,
        )

        async with self._lock:
            if resolved_session_id in self._sessions:
                raise FabricSessionAlreadyExistsError(f"Fabric session '{resolved_session_id}' is already registered.")
            self._sessions[resolved_session_id] = session
        return session

    async def get(self, session_id: str) -> FabricRuntimeSession:
        """Return an active session and update its last-accessed time."""
        async with self._lock:
            try:
                session = self._sessions[session_id]
            except KeyError as error:
                raise FabricSessionNotFoundError(f"Fabric session '{session_id}' was not found.") from error
            session.last_accessed_at = time.monotonic()
            return session

    async def remove(self, session_id: str) -> FabricRuntimeSession | None:
        """Remove and return a session without stopping its runtime."""
        async with self._lock:
            return self._sessions.pop(session_id, None)

    async def count(self) -> int:
        """Return the number of registered logical sessions."""
        async with self._lock:
            return len(self._sessions)
