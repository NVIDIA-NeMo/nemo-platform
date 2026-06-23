# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the debounced experiment rollup refresher."""

from __future__ import annotations

from typing import cast

import pytest
from nmp.common.entities.client import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.intake.entities.experiments import Experiment
from nmp.intake.spans.experiment_rollup_refresher import ExperimentRollupRefresher
from nmp.intake.spans.experiment_rollup_repository import (
    ExperimentRollup,
    ExperimentRollupRepository,
    ScoreRollup,
    metrics_to_rollup,
    rollup_to_metrics,
)


def _sample_rollup(experiment_id: str) -> ExperimentRollup:
    return ExperimentRollup(
        experiment_id=experiment_id,
        run_count=3,
        model_names=["provider/model"],
        agent_names=["agent"],
        agent_versions=["1.0"],
        evaluator_scores={"reward": ScoreRollup(sum=2.0, mean=0.667, median=1.0, p90=1.0, p95=1.0, p99=1.0, count=3)},
        cost_usd=ScoreRollup(sum=0.6, mean=0.2, median=0.2, p90=0.3, p95=0.3, p99=0.3, count=3),
        latency_ms=ScoreRollup(sum=3000.0, mean=1000.0, median=1000.0, p90=1500.0, p95=1500.0, p99=1500.0, count=3),
    )


class _FakeRollupRepo:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self._error = error

    async def get_rollups(self, *, workspace: str, experiment_ids: list[str]) -> dict[str, ExperimentRollup]:
        self.calls.append((workspace, list(experiment_ids)))
        if self._error is not None:
            raise self._error
        return {experiment_id: _sample_rollup(experiment_id) for experiment_id in experiment_ids}


class _FakeEntityClient:
    def __init__(self, *, get_error: Exception | None = None, update_error: Exception | None = None) -> None:
        self.updated: list[Experiment] = []
        self.get_calls: list[tuple[str, str]] = []
        self._get_error = get_error
        self._update_error = update_error

    async def get(self, entity_type: type[Experiment], *, name: str, workspace: str) -> Experiment:
        self.get_calls.append((name, workspace))
        if self._get_error is not None:
            raise self._get_error
        return Experiment(name=name, workspace=workspace, experiment_group_id="grp", dataset_name="ds")

    async def update(self, entity: Experiment) -> Experiment:
        if self._update_error is not None:
            raise self._update_error
        self.updated.append(entity)
        return entity


def _refresher(repo: _FakeRollupRepo, entity_client: _FakeEntityClient) -> ExperimentRollupRefresher:
    return ExperimentRollupRefresher(
        rollup_repository=cast(ExperimentRollupRepository, repo),
        entity_client=cast(EntityClient, entity_client),
        interval_seconds=999,
    )


def test_rollup_metrics_round_trip() -> None:
    rollup = _sample_rollup("exp-1")
    restored = metrics_to_rollup("exp-1", rollup_to_metrics(rollup, refreshed_at="2026-06-23T00:00:00+00:00"))
    assert restored.run_count == rollup.run_count
    assert restored.model_names == rollup.model_names
    assert restored.evaluator_scores["reward"] == rollup.evaluator_scores["reward"]
    assert restored.cost_usd == rollup.cost_usd
    assert restored.latency_ms == rollup.latency_ms


@pytest.mark.asyncio
async def test_flush_writes_denormalized_metrics() -> None:
    repo = _FakeRollupRepo()
    entity_client = _FakeEntityClient()
    refresher = _refresher(repo, entity_client)

    refresher.mark_dirty(workspace="default", experiment_id="exp-a")
    refresher.mark_dirty(workspace="default", experiment_id="exp-b")
    await refresher.flush()

    # One batched rollup query for the workspace, covering both dirty experiments.
    assert len(repo.calls) == 1
    workspace, ids = repo.calls[0]
    assert workspace == "default"
    assert set(ids) == {"exp-a", "exp-b"}

    # Each experiment got its metrics written, and the dirty set is drained.
    assert {entity.name for entity in entity_client.updated} == {"exp-a", "exp-b"}
    written = entity_client.updated[0].metrics
    assert written is not None
    assert written["version"] == 1
    assert written["run_count"] == 3
    assert written["evaluators"]["reward"]["mean"] == pytest.approx(0.667)
    assert written["cost_usd"]["mean"] == pytest.approx(0.2)
    assert "refreshed_at" in written
    assert refresher.pending() == set()


def test_mark_dirty_dedupes() -> None:
    refresher = _refresher(_FakeRollupRepo(), _FakeEntityClient())
    refresher.mark_dirty(workspace="default", experiment_id="exp-a")
    refresher.mark_dirty(workspace="default", experiment_id="exp-a")
    assert refresher.pending() == {("default", "exp-a")}


@pytest.mark.asyncio
async def test_flush_noop_when_clean() -> None:
    repo = _FakeRollupRepo()
    await _refresher(repo, _FakeEntityClient()).flush()
    assert repo.calls == []


@pytest.mark.asyncio
async def test_missing_experiment_is_skipped() -> None:
    entity_client = _FakeEntityClient(get_error=EntityNotFoundError("gone"))
    refresher = _refresher(_FakeRollupRepo(), entity_client)
    refresher.mark_dirty(workspace="default", experiment_id="exp-a")
    await refresher.flush()
    assert entity_client.updated == []
    assert refresher.pending() == set()  # not re-queued; the experiment no longer exists


@pytest.mark.asyncio
async def test_update_conflict_requeues() -> None:
    entity_client = _FakeEntityClient(update_error=EntityConflictError("version mismatch"))
    refresher = _refresher(_FakeRollupRepo(), entity_client)
    refresher.mark_dirty(workspace="default", experiment_id="exp-a")
    await refresher.flush()
    # A concurrent edit won the optimistic lock; the experiment is re-queued for the next cycle.
    assert refresher.pending() == {("default", "exp-a")}


@pytest.mark.asyncio
async def test_rollup_query_failure_requeues() -> None:
    repo = _FakeRollupRepo(error=RuntimeError("clickhouse down"))
    refresher = _refresher(repo, _FakeEntityClient())
    refresher.mark_dirty(workspace="default", experiment_id="exp-a")
    await refresher.flush()
    assert refresher.pending() == {("default", "exp-a")}
