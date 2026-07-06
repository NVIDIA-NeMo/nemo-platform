# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment group default metric sort: string storage/validation and the sort helper.

``default_metric_sort`` is a single ``sort``-param string (e.g. ``-cost_usd.mean``) stored on the
group. The client reads it and applies it as the list ``sort`` param; the list endpoint itself never
consults it. The ``_sort_experiments`` helper remains multi-key capable (pinned-first + tiebreaks),
so its unit tests still exercise lists.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from nmp.intake.api.v2.experiments.endpoints import _sort_experiments, _validate_default_metric_sort
from nmp.intake.api.v2.experiments.schemas import EvaluatorAggregate, ExperimentResponse

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


def test_falls_back_to_created_at_when_sorted_metric_missing() -> None:
    rows = [
        _exp("old", created=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _exp("new", created=datetime(2026, 6, 1, tzinfo=timezone.utc)),
    ]
    # No cost rollup on either -> the appended -created_at key decides (newest first).
    ordered = _sort_experiments(rows, keys=[("cost_usd.mean", False), ("created_at", True)])
    assert _names(ordered) == ["new", "old"]


# ----------------------------- default-sort validation -----------------------------


def test_validate_default_metric_sort_accepts_metric_fields() -> None:
    # Both ascending and descending ('-') sort-param strings are valid.
    for value in ("cost_usd.mean", "-latency_ms.p95", "run_count", "-evaluators.harbor.verifier.mean"):
        _validate_default_metric_sort(value)
    _validate_default_metric_sort(None)  # absent default sort is fine


def test_validate_default_metric_sort_rejects_non_metric_fields() -> None:
    for value in ("name", "-created_at", "cost_usd.bogus", "evaluators.reward"):
        with pytest.raises(HTTPException) as exc:
            _validate_default_metric_sort(value)
        assert exc.value.status_code == 400


def test_entity_ignores_legacy_default_sort_key() -> None:
    # Rows persisted under the old `default_sort` list key must still deserialize; the renamed
    # `default_metric_sort` field is simply absent (None), and the stale key is ignored.
    from nmp.intake.entities.experiments import ExperimentGroup

    group = ExperimentGroup.model_validate(
        {
            "name": "g",
            "workspace": "default",
            "default_sort": [{"field": "cost_usd.mean", "direction": "asc"}],
        }
    )
    assert group.default_metric_sort is None


# ----------------------------- endpoint wiring -----------------------------


def test_create_group_with_default_sort_round_trips(client: TestClient) -> None:
    resp = client.post(GROUPS, json={"name": "g-sort", "default_metric_sort": "-cost_usd.mean"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["default_metric_sort"] == "-cost_usd.mean"


def test_create_group_rejects_non_metric_sort_field(client: TestClient) -> None:
    for value in ("name", "-created_at", "cost_usd.bogus"):
        resp = client.post(GROUPS, json={"name": f"g-{value.lstrip('-')}", "default_metric_sort": value})
        assert resp.status_code == 400, resp.text


def test_default_order_floats_pinned_first(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "g-pin"}).json()
    for name in ("exp-a", "exp-b"):
        created = client.post(
            EXPERIMENTS, json={"name": name, "experiment_group_id": group["id"], "dataset_name": "ds"}
        )
        assert created.status_code == 201, created.text
    # Pin the OLDER experiment (exp-a): by the -created_at fallback it would sort LAST, so seeing it
    # first proves pinned-first actually overrides the fallback rather than coinciding with newest-first.
    assert client.post(f"{EXPERIMENTS}/exp-a/pin").status_code == 200
    # No explicit sort -> default path floats pinned to top (entity-only, no rollups needed).
    listed = client.get(EXPERIMENTS, params={"filter[experiment_group_id]": group["id"]})
    assert listed.status_code == 200, listed.text
    assert [r["name"] for r in listed.json()["data"]] == ["exp-a", "exp-b"]
