# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optional fields on ExperimentGroup (insight_id, summary, metadata) and Experiment
(parent_experiment_id, status, root_cause): round-trip through create/update, parent-reference
validation, and free-form status."""

from fastapi.testclient import TestClient

EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _group(client: TestClient, name: str = "grp") -> dict:
    resp = client.post(GROUPS, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _experiment(client: TestClient, group_id: str, name: str) -> dict:
    resp = client.post(EXPERIMENTS, json={"name": name, "experiment_group_id": group_id, "dataset_name": "ds"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_group_fields_round_trip(client: TestClient) -> None:
    resp = client.post(
        GROUPS,
        json={"name": "g1", "insight_id": "insight-123", "summary": "looks promising", "metadata": {"k": "v"}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["insight_id"] == "insight-123"
    assert body["summary"] == "looks promising"
    assert body["metadata"] == {"k": "v"}


def test_experiment_fields_round_trip(client: TestClient) -> None:
    group = _group(client)
    parent = _experiment(client, group["id"], "exp-parent")
    resp = client.post(
        EXPERIMENTS,
        json={
            "name": "exp-1",
            "experiment_group_id": group["id"],
            "dataset_name": "ds",
            "parent_experiment_id": parent["id"],
            "status": "running",
            "root_cause": "still evaluating",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parent_experiment_id"] == parent["id"]
    assert body["status"] == "running"
    assert body["root_cause"] == "still evaluating"


def test_experiment_rejects_unknown_parent(client: TestClient) -> None:
    group = _group(client)
    resp = client.post(
        EXPERIMENTS,
        json={
            "name": "exp-orphan",
            "experiment_group_id": group["id"],
            "dataset_name": "ds",
            "parent_experiment_id": "does-not-exist",
        },
    )
    assert resp.status_code == 400, resp.text


def test_update_rejects_unknown_parent(client: TestClient) -> None:
    group = _group(client)
    _experiment(client, group["id"], "exp-u")
    updated = client.put(
        f"{EXPERIMENTS}/exp-u",
        json={
            "name": "exp-u",
            "experiment_group_id": group["id"],
            "dataset_name": "ds",
            "parent_experiment_id": "does-not-exist",
        },
    )
    assert updated.status_code == 400, updated.text


def test_status_is_a_free_string(client: TestClient) -> None:
    # status is producer-defined, not a fixed enum — any string is accepted.
    group = _group(client)
    resp = client.post(
        EXPERIMENTS,
        json={"name": "exp-custom", "experiment_group_id": group["id"], "dataset_name": "ds", "status": "my-own-state"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "my-own-state"


def test_experiment_status_and_root_cause_update(client: TestClient) -> None:
    group = _group(client)
    _experiment(client, group["id"], "exp-3")
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


def test_filter_experiments_by_metadata(client: TestClient) -> None:
    group = _group(client, name="g-meta")
    for name, model in (("exp-claude", "claude-opus"), ("exp-gpt", "gpt-5")):
        resp = client.post(
            EXPERIMENTS,
            json={
                "name": name,
                "experiment_group_id": group["id"],
                "dataset_name": "ds",
                "metadata": {"model": model, "lane": "gold"},
            },
        )
        assert resp.status_code == 201, resp.text

    # A distinct value narrows to the one experiment that has it.
    only_claude = client.get(EXPERIMENTS, params={"filter[metadata.model]": "claude-opus"})
    assert only_claude.status_code == 200, only_claude.text
    assert [e["name"] for e in only_claude.json()["data"]] == ["exp-claude"]

    # A shared value returns both.
    both = client.get(EXPERIMENTS, params={"filter[metadata.lane]": "gold"})
    assert {e["name"] for e in both.json()["data"]} == {"exp-claude", "exp-gpt"}


def test_filter_experiment_groups_by_metadata(client: TestClient) -> None:
    for name, team in (("grp-sy", "switchyard"), ("grp-opt", "optimizer")):
        resp = client.post(GROUPS, json={"name": name, "metadata": {"team": team}})
        assert resp.status_code == 201, resp.text

    listed = client.get(GROUPS, params={"filter[metadata.team]": "switchyard"})
    assert listed.status_code == 200, listed.text
    assert [g["name"] for g in listed.json()["data"]] == ["grp-sy"]


def test_new_fields_are_optional(client: TestClient) -> None:
    # Omitting every new field is valid; they default to null.
    gbody = _group(client, name="g-min")
    assert gbody["insight_id"] is None and gbody["summary"] is None and gbody["metadata"] is None

    ebody = _experiment(client, gbody["id"], "exp-min")
    assert ebody["parent_experiment_id"] is None and ebody["status"] is None and ebody["root_cause"] is None
