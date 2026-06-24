# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Endpoint-level guards for the experiments list sort (rollups unavailable / bad field).

The shared ``client`` fixture overrides ``get_experiment_rollup_repository`` to return ``None``,
which is exactly the "ClickHouse disabled / unavailable" condition. A metric-backed sort cannot be
computed without rollups, so it must fail loudly rather than silently degrade to name order.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _make_experiment(client: TestClient, name: str = "exp-1", group: str = "grp-1") -> None:
    group_resp = client.post(GROUPS, json={"name": group})
    assert group_resp.status_code == 201, group_resp.text
    exp_resp = client.post(
        EXPERIMENTS,
        json={"name": name, "experiment_group_id": group_resp.json()["id"], "dataset_name": "ds"},
    )
    assert exp_resp.status_code == 201, exp_resp.text


def test_metric_sort_returns_503_when_rollups_unavailable(client: TestClient) -> None:
    _make_experiment(client)
    response = client.get(EXPERIMENTS, params={"sort": "-cost_usd.mean"})
    assert response.status_code == 503, response.text


def test_run_count_sort_returns_503_when_rollups_unavailable(client: TestClient) -> None:
    _make_experiment(client)
    response = client.get(EXPERIMENTS, params={"sort": "run_count"})
    assert response.status_code == 503, response.text


def test_entity_sort_still_succeeds_without_rollups(client: TestClient) -> None:
    _make_experiment(client)
    for sort in ("name", "-created_at", "pinned_at"):
        response = client.get(EXPERIMENTS, params={"sort": sort})
        assert response.status_code == 200, response.text


def test_unknown_sort_field_returns_400(client: TestClient) -> None:
    response = client.get(EXPERIMENTS, params={"sort": "bogus.field"})
    assert response.status_code == 400, response.text
