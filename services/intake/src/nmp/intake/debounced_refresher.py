# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic debounced, coalescing background refresher.

Owns *how* a background refresh runs — a coalescing dirty set of keys, a periodic drain loop with an
interruptible sleep, and a managed start/stop lifecycle with a graceful final drain — independent of
*what* the work is. Subclasses implement :meth:`_process` with the domain logic and re-queue failures
via :meth:`_enqueue`.

This has no intake-specific dependencies; it lives here for now but is a candidate to move to
``nmp.common`` once a second consumer needs the same pattern.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

KeyT = TypeVar("KeyT")

# stop()'s final flush can itself re-queue keys (a transient failure/conflict in _process that would
# clear on retry), so it drains up to this many passes; keys still queued afterwards are logged.
_STOP_DRAIN_PASSES = 3


class DebouncedRefresher(ABC, Generic[KeyT]):
    """Coalesces dirty keys and processes them in batches on a fixed cadence.

    A burst of :meth:`_enqueue` calls for the same key within an interval collapses to a single batch
    entry, and enqueuing never blocks (it's a plain set add), so the hot path (e.g. request handling)
    is never gated on the work. Subclasses implement :meth:`_process`.
    """

    def __init__(self, *, interval_seconds: float = 10.0) -> None:
        self._interval_seconds = interval_seconds
        self._dirty: set[KeyT] = set()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def _enqueue(self, key: KeyT) -> None:
        """Queue a key for the next batch. Cheap and non-blocking; safe to call from any async context."""
        self._dirty.add(key)

    def pending(self) -> set[KeyT]:
        """Return a copy of the currently-queued keys (for observability/tests)."""
        return set(self._dirty)

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        # Signal the loop to exit and let it finish any in-flight flush — we never cancel mid-flush, so a
        # detached batch can't be dropped before it's written. Then drain what's left in a bounded number
        # of passes, since the final flush can re-queue keys itself.
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None
        for _ in range(_STOP_DRAIN_PASSES):
            if not self._dirty:
                return
            await self.flush()
        if self._dirty:
            logger.warning(
                "%s stopped with %d key(s) still queued after %d drain passes; not retried before shutdown",
                type(self).__name__,
                len(self._dirty),
                _STOP_DRAIN_PASSES,
            )

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                # Interruptible sleep: wakes early when stop() sets the event so shutdown is prompt.
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval_seconds)
            except asyncio.TimeoutError:
                pass  # interval elapsed; time for a periodic flush
            try:
                await self.flush()
            except Exception:
                logger.exception("%s refresh cycle failed", type(self).__name__)

    async def flush(self) -> None:
        """Drain the dirty set and hand the batch to :meth:`_process`. Directly callable for tests."""
        if not self._dirty:
            return
        batch = self._dirty
        self._dirty = set()
        await self._process(batch)

    @abstractmethod
    async def _process(self, batch: set[KeyT]) -> None:
        """Process a drained batch of dirty keys. Re-queue any that should retry via :meth:`_enqueue`."""
