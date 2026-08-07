# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Background worker that denormalizes name fields from ClickHouse onto Evaluation entities.

Ingest marks ``(workspace, evaluation_id)`` dirty — a cheap, non-blocking set add. A background loop
drains the dirty set on a fixed interval, recomputes each touched evaluation's rollup, and writes the
distinct ``agent_names``/``agent_versions``/``model_names`` sets onto the (system-managed) fields of
its Evaluation entity. That lets the workspace-wide Evaluations list filter by agent/model name against
the entity store (``$contains``) instead of scanning the ClickHouse session table on every request.

This is a deliberately narrowed descendant of the closed PR #424 rollup refresher: it denormalizes
only the name fields, not the computed metric rollups. Names are raw observed strings with no formula,
so a change to how any aggregate is computed never invalidates them — the staleness/backfill hazard
that made denormalizing metrics not worth it (ASE-319) does not apply here. Bursts coalesce: many
ingests for one evaluation within an interval collapse to a single recompute, and ingest latency is
never gated on the rollup query.
"""

from __future__ import annotations

import asyncio
import logging

from nmp.common.entities.client import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.intake.entities.experiments import Experiment
from nmp.intake.repository.evaluation_rollup import EvaluationRollup, EvaluationRollupRepository

logger = logging.getLogger(__name__)


class EvaluationDenormalizer:
    """Coalesces dirty evaluation ids and refreshes their denormalized name fields on a fixed cadence."""

    def __init__(
        self,
        *,
        rollup_repository: EvaluationRollupRepository,
        entity_client: EntityClient,
        interval_seconds: float = 10.0,
    ) -> None:
        self._rollup_repository = rollup_repository
        self._entity_client = entity_client
        self._interval_seconds = interval_seconds
        self._dirty: set[tuple[str, str]] = set()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def mark_dirty(self, *, workspace: str, evaluation_id: str) -> None:
        """Queue an evaluation for refresh. Cheap and non-blocking; safe to call from the ingest path."""
        self._dirty.add((workspace, evaluation_id))

    def pending(self) -> set[tuple[str, str]]:
        """Return a copy of the currently-queued ``(workspace, evaluation_id)`` pairs (observability/tests)."""
        return set(self._dirty)

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        # Signal the loop to exit and let it finish any in-flight flush — we never cancel mid-flush, so a
        # detached batch can't be dropped before it's written. Then a final drain covers the cases the loop
        # can't (it saw the stop flag before its first flush, or items were enqueued during the last flush).
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None
        await self.flush()

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
                logger.exception("Evaluation denormalization cycle failed")

    async def flush(self) -> None:
        """Drain the dirty set and write current name fields. Directly callable for deterministic tests."""
        if not self._dirty:
            return
        batch = self._dirty
        self._dirty = set()
        by_workspace: dict[str, list[str]] = {}
        for workspace, evaluation_id in batch:
            by_workspace.setdefault(workspace, []).append(evaluation_id)
        for workspace, evaluation_ids in by_workspace.items():
            try:
                await self._refresh_workspace(workspace, evaluation_ids)
            except Exception:
                # Re-queue the whole workspace batch for the next cycle (e.g. ClickHouse unavailable).
                logger.exception("Failed to refresh evaluation names for workspace %s; re-queuing", workspace)
                for evaluation_id in evaluation_ids:
                    self._dirty.add((workspace, evaluation_id))

    async def _refresh_workspace(self, workspace: str, evaluation_ids: list[str]) -> None:
        rollups = await self._rollup_repository.get_rollups(workspace=workspace, evaluation_ids=evaluation_ids)
        for evaluation_id in evaluation_ids:
            rollup = rollups.get(evaluation_id)
            if rollup is None:
                continue
            await self._write_names(workspace, evaluation_id, rollup)

    async def _write_names(self, workspace: str, evaluation_id: str, rollup: EvaluationRollup) -> None:
        try:
            evaluation = await self._entity_client.get(Experiment, name=evaluation_id, workspace=workspace)
        except EntityNotFoundError:
            # Deleted between ingest and refresh; nothing to update.
            return
        # Skip the write when nothing changed, so a burst of re-ingests that add no new names doesn't
        # churn the entity store (and doesn't lose an optimistic-lock race for no reason).
        if (
            evaluation.agent_names == rollup.agent_names
            and evaluation.agent_versions == rollup.agent_versions
            and evaluation.model_names == rollup.model_names
        ):
            return
        evaluation.agent_names = rollup.agent_names
        evaluation.agent_versions = rollup.agent_versions
        evaluation.model_names = rollup.model_names
        try:
            await self._entity_client.update(evaluation)
        except EntityConflictError:
            # A concurrent user edit won the optimistic lock; re-queue for the next cycle.
            self._dirty.add((workspace, evaluation_id))
