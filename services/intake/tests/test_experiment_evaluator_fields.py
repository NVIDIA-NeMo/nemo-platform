# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Evaluator fields on ExperimentGroup (insight_id, summary, metadata) and Experiment
(parent_experiment_id, status, root_cause). All are optional and round-trip through create/update."""

from fastapi.testclient import TestClient

EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _group(client: TestClient, name: str = "grp") -> dict:
    resp = client.post(GROUPS, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_group_evaluator_fields_round_trip(client: TestClient) -> None:
    resp = client.post(
        GROUPS,
        json={"name": "g1", "insight_id": "insight-123", "summary": "looks promising", "metadata": {"k": "v"}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["insight_id"] == "insight-123"
    assert body["summary"] == "looks promising"
    assert body["metadata"] == {"k": "v"}


def test_experiment_evaluator_fields_round_trip(client: TestClient) -> None:
    group = _group(client)
    resp = client.post(
        EXPERIMENTS,
        json={
            "name": "exp-1",
            "experiment_group_id": group["id"],
            "dataset_name": "ds",
            "parent_experiment_id": "exp-0",
            "status": "running",
            "root_cause": "still evaluating",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parent_experiment_id"] == "exp-0"
    assert body["status"] == "running"
    assert body["root_cause"] == "still evaluating"


def test_experiment_rejects_invalid_status(client: TestClient) -> None:
    group = _group(client)
    resp = client.post(
        EXPERIMENTS,
        json={"name": "exp-bad", "experiment_group_id": group["id"], "dataset_name": "ds", "status": "bogus"},
    )
    assert resp.status_code == 422, resp.text


def test_experiment_status_and_root_cause_update(client: TestClient) -> None:
    group = _group(client)
    client.post(
        EXPERIMENTS,
        json={"name": "exp-3", "experiment_group_id": group["id"], "dataset_name": "ds", "status": "baseline"},
    )
    updated = client.put(
        f"{EXPERIMENTS}/exp-3",
        json={
            "name": "exp-3",
            "experiment_group_id": group["id"],
            "dataset_name": "ds",
            "status": "winner",
            "root_cause": "best cost/accuracy trade-off",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "winner"
    assert updated.json()["root_cause"] == "best cost/accuracy trade-off"


def test_new_fields_are_optional(client: TestClient) -> None:
    # Omitting every new field is valid; they default to null.
    group = client.post(GROUPS, json={"name": "g-min"})
    assert group.status_code == 201, group.text
    gbody = group.json()
    assert gbody["insight_id"] is None and gbody["summary"] is None and gbody["metadata"] is None

    exp = client.post(EXPERIMENTS, json={"name": "exp-min", "experiment_group_id": gbody["id"], "dataset_name": "ds"})
    assert exp.status_code == 201, exp.text
    ebody = exp.json()
    assert ebody["parent_experiment_id"] is None and ebody["status"] is None and ebody["root_cause"] is None
