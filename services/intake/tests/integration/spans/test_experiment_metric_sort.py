# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The experiments list ranks by a ClickHouse rollup metric (Option A app-merge), end to end."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

ATIF_INGEST = "/apis/intake/v2/workspaces/default/ingest/atif"
EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _ensure_group(client: TestClient, name: str = "metric-sort-group") -> str:
    response = client.post(GROUPS, json={"name": name})
    if response.status_code == 409:
        response = client.get(f"{GROUPS}/{name}")
    response.raise_for_status()
    return response.json()["id"]


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _atif_body(*, started_at: datetime, experiment_id: str, cost_usd: float, offset_seconds: int) -> dict[str, Any]:
    session_started_at = started_at + timedelta(seconds=offset_seconds)
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": f"{experiment_id}-session",
        "experiment_context": {"experiment_id": experiment_id, "test_case_id": "case-1"},
        "extra": {"task_name": "case-1", "verifier_result": {"rewards": {"reward": 1.0}}},
        "agent": {"name": "sample-agent", "version": "1.0.0", "model_name": "provider/sample-model"},
        "steps": [
            {
                "step_id": 1,
                "timestamp": _iso(session_started_at),
                "source": "agent",
                "model_name": "provider/sample-model",
                "message": "done",
                "metrics": {"prompt_tokens": 100, "completion_tokens": 10, "cost_usd": cost_usd},
            }
        ],
    }


def _create_experiment(client: TestClient, group_id: str, name: str) -> None:
    response = client.post(
        EXPERIMENTS,
        json={"name": name, "experiment_group_id": group_id, "dataset_name": "ds"},
    )
    assert response.status_code == 201, response.text


def test_list_sorts_by_cost_metric_missing_last(client: TestClient) -> None:
    group_id = _ensure_group(client)
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    for index, (name, cost) in enumerate([("exp-cheap", 0.10), ("exp-pricey", 0.90), ("exp-mid", 0.50)]):
        _create_experiment(client, group_id, name)
        response = client.post(
            ATIF_INGEST,
            json=_atif_body(started_at=started_at, experiment_id=name, cost_usd=cost, offset_seconds=index * 10),
        )
        assert response.status_code == 201, response.text
    # No ingest -> no cost rollup -> must sort last regardless of direction.
    _create_experiment(client, group_id, "exp-norun")

    listed = client.get(EXPERIMENTS, params={"sort": "-cost_usd.mean", "page_size": 50})
    assert listed.status_code == 200, listed.text
    names = [row["name"] for row in listed.json()["data"]]
    assert names == ["exp-pricey", "exp-mid", "exp-cheap", "exp-norun"]


def test_list_rejects_unknown_sort_field(client: TestClient) -> None:
    response = client.get(EXPERIMENTS, params={"sort": "bogus.field"})
    assert response.status_code == 400, response.text
