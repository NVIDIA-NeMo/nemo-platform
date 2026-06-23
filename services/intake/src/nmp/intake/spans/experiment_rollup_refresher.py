# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Background worker that denormalizes ClickHouse rollups onto Experiment entities.

Ingest marks ``(workspace, experiment_id)`` dirty — a cheap, non-blocking set add. A
background loop drains the dirty set on a fixed interval, recomputes each touched
experiment's rollup via ``get_rollups`` (which uses ``FINAL``, so it's correct under
re-ingest), and writes the summary onto the experiment's system-managed ``metrics``
field. Bursts coalesce: many ingests for one experiment within an interval collapse to a
single recompute, and ingest latency is never gated on the rollup query.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from nmp.common.entities.client import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.intake.entities.experiments import Experiment
from nmp.intake.spans.experiment_rollup_repository import ExperimentRollupRepository, rollup_to_metrics

logger = logging.getLogger(__name__)


class ExperimentRollupRefresher:
    """Coalesces dirty experiment ids and refreshes their denormalized ``metrics`` on a fixed cadence."""

    def __init__(
        self,
        *,
        rollup_repository: ExperimentRollupRepository,
        entity_client: EntityClient,
        interval_seconds: float = 10.0,
    ) -> None:
        self._rollup_repository = rollup_repository
        self._entity_client = entity_client
        self._interval_seconds = interval_seconds
        self._dirty: set[tuple[str, str]] = set()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def mark_dirty(self, *, workspace: str, experiment_id: str) -> None:
        """Queue an experiment for refresh. Cheap and non-blocking; safe to call from the ingest path."""
        self._dirty.add((workspace, experiment_id))

    def pending(self) -> set[tuple[str, str]]:
        """Return a copy of the currently-queued ``(workspace, experiment_id)`` pairs (for observability/tests)."""
        return set(self._dirty)

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # Best-effort final drain so an in-flight burst isn't lost on shutdown.
        await self.flush()

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.sleep(self._interval_seconds)
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Experiment rollup refresh cycle failed")

    async def flush(self) -> None:
        """Drain the dirty set and write current rollups. Directly callable for deterministic tests."""
        if not self._dirty:
            return
        batch = self._dirty
        self._dirty = set()
        by_workspace: dict[str, list[str]] = {}
        for workspace, experiment_id in batch:
            by_workspace.setdefault(workspace, []).append(experiment_id)
        for workspace, experiment_ids in by_workspace.items():
            try:
                await self._refresh_workspace(workspace, experiment_ids)
            except Exception:
                # Re-queue the whole workspace batch for the next cycle (e.g. ClickHouse unavailable).
                logger.exception("Failed to refresh experiment rollups for workspace %s; re-queuing", workspace)
                for experiment_id in experiment_ids:
                    self._dirty.add((workspace, experiment_id))

    async def _refresh_workspace(self, workspace: str, experiment_ids: list[str]) -> None:
        rollups = await self._rollup_repository.get_rollups(workspace=workspace, experiment_ids=experiment_ids)
        refreshed_at = datetime.now(timezone.utc).isoformat()
        for experiment_id in experiment_ids:
            rollup = rollups.get(experiment_id)
            if rollup is None:
                continue
            await self._write_metrics(workspace, experiment_id, rollup_to_metrics(rollup, refreshed_at=refreshed_at))

    async def _write_metrics(self, workspace: str, experiment_id: str, metrics: dict) -> None:
        try:
            experiment = await self._entity_client.get(Experiment, name=experiment_id, workspace=workspace)
        except EntityNotFoundError:
            # Deleted between ingest and refresh; nothing to update.
            return
        experiment.metrics = metrics
        try:
            await self._entity_client.update(experiment)
        except EntityConflictError:
            # A concurrent user edit won the optimistic lock; re-queue for the next cycle.
            self._dirty.add((workspace, experiment_id))
