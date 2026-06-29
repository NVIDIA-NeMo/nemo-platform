# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment group ranking: multi-key default sort, pinned-first, fallback, and validation.

The shared ``client`` fixture overrides the rollup repository to ``None`` (ClickHouse unavailable),
which lets us verify that a metric-based *default* ranking degrades to ``-created_at`` instead of
failing — distinct from an explicit metric sort, which still 503s.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from nmp.intake.api.v2.experiments.endpoints import _sort_experiments, _validate_ranking
from nmp.intake.api.v2.experiments.schemas import EvaluatorAggregate, ExperimentResponse
from nmp.intake.entities.experiments import RankingField

EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _exp(
    name: str,
    *,
    cost: float | None = None,
    latency: float | None = None,
    pinned: bool = False,
    created: datetime | None = None,
) -> ExperimentResponse:
    return ExperimentResponse(
        id=name,
        name=name,
        workspace="default",
        experiment_group_id="grp",
        dataset_name="ds",
        cost_usd=EvaluatorAggregate(mean=cost) if cost is not None else None,
        latency_ms=EvaluatorAggregate(mean=latency) if latency is not None else None,
        pinned_at=datetime(2026, 1, 1, tzinfo=timezone.utc) if pinned else None,
        created_at=created,
    )


def _names(responses: list[ExperimentResponse]) -> list[str]:
    return [r.name for r in responses]


# ----------------------------- multi-key sort -----------------------------


def test_multi_key_primary_then_tiebreak() -> None:
    # Primary cost asc; ties on cost broken by latency asc.
    rows = [_exp("a", cost=1.0, latency=200), _exp("b", cost=1.0, latency=100), _exp("c", cost=0.5, latency=999)]
    ordered = _sort_experiments(rows, keys=[("cost_usd.mean", False), ("latency_ms.mean", False)])
    assert _names(ordered) == ["c", "b", "a"]


def test_pinned_floats_to_top() -> None:
    rows = [_exp("a", cost=0.1), _exp("pinned", cost=0.9, pinned=True), _exp("b", cost=0.5)]
    ordered = _sort_experiments(rows, keys=[("cost_usd.mean", False)], pinned_first=True)
    # Pinned first regardless of metric; unpinned follow in cost order.
    assert _names(ordered) == ["pinned", "a", "b"]


def test_falls_back_to_created_at_when_ranked_metric_missing() -> None:
    rows = [
        _exp("old", created=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _exp("new", created=datetime(2026, 6, 1, tzinfo=timezone.utc)),
    ]
    # No cost rollup on either -> the appended -created_at key decides (newest first).
    ordered = _sort_experiments(rows, keys=[("cost_usd.mean", False), ("created_at", True)])
    assert _names(ordered) == ["new", "old"]


# ----------------------------- ranking validation -----------------------------


def test_validate_ranking_accepts_metric_fields() -> None:
    _validate_ranking(
        [
            RankingField(field="cost_usd.mean", direction="asc"),
            RankingField(field="latency_ms.p95", direction="asc"),
            RankingField(field="run_count", direction="desc"),
            RankingField(field="evaluators.harbor.verifier.mean", direction="desc"),
        ]
    )


def test_validate_ranking_rejects_non_metric_fields() -> None:
    for field in ("name", "created_at", "cost_usd.bogus", "evaluators.reward"):
        with pytest.raises(HTTPException) as exc:
            _validate_ranking([RankingField(field=field, direction="asc")])
        assert exc.value.status_code == 400


# ----------------------------- endpoint wiring -----------------------------


def test_create_group_with_ranking_round_trips(client: TestClient) -> None:
    resp = client.post(GROUPS, json={"name": "g-rank", "ranking": [{"field": "cost_usd.mean", "direction": "asc"}]})
    assert resp.status_code == 201, resp.text
    assert resp.json()["ranking"] == [{"field": "cost_usd.mean", "direction": "asc"}]


def test_create_group_rejects_non_metric_ranking_field(client: TestClient) -> None:
    for field in ("name", "created_at", "cost_usd.bogus"):
        resp = client.post(GROUPS, json={"name": f"g-{field}", "ranking": [{"field": field, "direction": "asc"}]})
        assert resp.status_code == 400, resp.text


def test_default_order_floats_pinned_first(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "g-pin"}).json()
    for name in ("exp-a", "exp-b"):
        created = client.post(
            EXPERIMENTS, json={"name": name, "experiment_group_id": group["id"], "dataset_name": "ds"}
        )
        assert created.status_code == 201, created.text
    assert client.post(f"{EXPERIMENTS}/exp-b/pin").status_code == 200
    # No explicit sort -> default path floats pinned to top (entity-only, no rollups needed).
    listed = client.get(EXPERIMENTS, params={"filter[experiment_group_id]": group["id"]})
    assert listed.status_code == 200, listed.text
    assert [r["name"] for r in listed.json()["data"]][0] == "exp-b"


def test_default_metric_ranking_degrades_without_rollups(client: TestClient) -> None:
    # Group ranks by a metric, but rollups are unavailable. The default sort must NOT 503 — it falls
    # back to -created_at (unlike an explicit metric sort, which does 503).
    group = client.post(
        GROUPS, json={"name": "g-deg", "ranking": [{"field": "cost_usd.mean", "direction": "asc"}]}
    ).json()
    client.post(EXPERIMENTS, json={"name": "e1", "experiment_group_id": group["id"], "dataset_name": "ds"})

    default_sorted = client.get(EXPERIMENTS, params={"filter[experiment_group_id]": group["id"]})
    assert default_sorted.status_code == 200, default_sorted.text

    explicit_metric = client.get(
        EXPERIMENTS, params={"filter[experiment_group_id]": group["id"], "sort": "-cost_usd.mean"}
    )
    assert explicit_metric.status_code == 503, explicit_metric.text
