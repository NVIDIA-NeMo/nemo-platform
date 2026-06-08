# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CRUD tests for the Experiments and ExperimentGroups endpoints."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.intake.api.v2.experiments.endpoints import get_experiment_rollup_repository

GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"
EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"


def _experiment_body(**overrides: Any) -> dict:
    body = {
        "name": "terminal-bench-2_claude-code_opus_baseline",
        "agent_name": "claude-code",
        "agent_version": "0.125.0",
        "dataset_name": "terminal-bench-2",
        "dataset_version": "v1",
        "source_link": "https://example.com/experiments/tb2-baseline",
        "metadata": {"job_name": "tb2-baseline"},
    }
    body.update(overrides)
    return body


def test_experiment_group_crud(client: TestClient) -> None:
    created = client.post(GROUPS, json={"name": "tb2-routing-research", "description": "routing sweep"})
    assert created.status_code == 201, created.text
    group = created.json()
    assert group["name"] == "tb2-routing-research"
    assert group["description"] == "routing sweep"
    assert group["id"]

    # Duplicate name conflicts.
    duplicate = client.post(GROUPS, json={"name": "tb2-routing-research"})
    assert duplicate.status_code == 409

    fetched = client.get(f"{GROUPS}/tb2-routing-research")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == group["id"]

    listed = client.get(GROUPS)
    assert listed.status_code == 200
    assert any(g["name"] == "tb2-routing-research" for g in listed.json()["data"])

    deleted = client.delete(f"{GROUPS}/tb2-routing-research")
    assert deleted.status_code == 204
    missing = client.get(f"{GROUPS}/tb2-routing-research")
    assert missing.status_code == 404


def test_experiment_group_update_description(client: TestClient) -> None:
    client.post(GROUPS, json={"name": "grp", "description": "old"})
    updated = client.put(f"{GROUPS}/grp", json={"name": "grp", "description": "new"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "new"
    # Renaming via PUT is rejected.
    renamed = client.put(f"{GROUPS}/grp", json={"name": "renamed"})
    assert renamed.status_code == 409
    missing = client.put(f"{GROUPS}/missing", json={"name": "missing"})
    assert missing.status_code == 404


def test_experiment_update_adds_to_group_and_edits(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "grp"}).json()
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-a"))

    # Add the existing (ungrouped) experiment to the group and edit its summary.
    body = _experiment_body(name="exp-a", experiment_group_id=group["id"], summary="looks good")
    updated = client.put(f"{EXPERIMENTS}/exp-a", json=body)
    assert updated.status_code == 200, updated.text
    assert updated.json()["experiment_group_id"] == group["id"]
    assert updated.json()["summary"] == "looks good"


def test_experiment_update_rejects_immutable_change(client: TestClient) -> None:
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-a", agent_name="claude-code"))
    changed = _experiment_body(name="exp-a", agent_name="cursor")
    resp = client.put(f"{EXPERIMENTS}/exp-a", json=changed)
    assert resp.status_code == 409, resp.text
    assert "agent_name" in resp.json()["detail"]
    missing = client.put(f"{EXPERIMENTS}/missing", json=_experiment_body(name="missing"))
    assert missing.status_code == 404


def test_experiment_crud_and_empty_rollups(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "grp"}).json()

    created = client.post(EXPERIMENTS, json=_experiment_body(experiment_group_id=group["id"]))
    assert created.status_code == 201, created.text
    exp = created.json()
    assert exp["name"] == "terminal-bench-2_claude-code_opus_baseline"
    assert exp["experiment_group_id"] == group["id"]
    assert exp["agent_name"] == "claude-code"
    assert exp["dataset_name"] == "terminal-bench-2"
    assert exp["source_link"] == "https://example.com/experiments/tb2-baseline"
    assert exp["metadata"] == {"job_name": "tb2-baseline"}

    # Rollups exist on the read model but are empty until ClickHouse hydration lands.
    assert exp["evaluator_names"] == []
    assert exp["model_names"] == []
    assert exp["aggregate_scores"] is None
    assert exp["run_count"] == 0


def test_experiment_read_degrades_when_rollup_hydration_fails(client: TestClient) -> None:
    class FailingRollupRepository:
        async def get_rollups(self, *, workspace: str, experiment_ids: list[str]) -> dict:
            raise RuntimeError("clickhouse unavailable")

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_experiment_rollup_repository] = lambda: FailingRollupRepository()
    try:
        created = client.post(EXPERIMENTS, json=_experiment_body(name="exp-rollup-fails"))
        assert created.status_code == 201, created.text

        fetched = client.get(f"{EXPERIMENTS}/exp-rollup-fails")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["name"] == "exp-rollup-fails"
        assert fetched.json()["run_count"] == 0
        assert fetched.json()["aggregate_scores"] is None
    finally:
        app.dependency_overrides.pop(get_experiment_rollup_repository, None)


def test_experiment_group_ref_is_soft(client: TestClient) -> None:
    # experiment_group_id is a soft reference: a non-existent group id is accepted.
    created = client.post(EXPERIMENTS, json=_experiment_body(experiment_group_id="grp-does-not-exist"))
    assert created.status_code == 201, created.text
    assert created.json()["experiment_group_id"] == "grp-does-not-exist"


def test_experiment_conflict_and_not_found(client: TestClient) -> None:
    created = client.post(EXPERIMENTS, json=_experiment_body())
    assert created.status_code == 201
    duplicate = client.post(EXPERIMENTS, json=_experiment_body())
    assert duplicate.status_code == 409
    missing = client.get(f"{EXPERIMENTS}/does-not-exist")
    assert missing.status_code == 404
    missing_delete = client.delete(f"{EXPERIMENTS}/does-not-exist")
    assert missing_delete.status_code == 404


def test_experiment_list_and_scope_to_group(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "grp"}).json()
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-a", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-b"))

    all_resp = client.get(EXPERIMENTS)
    assert all_resp.status_code == 200
    names = {e["name"] for e in all_resp.json()["data"]}
    assert {"exp-a", "exp-b"} <= names

    in_group = client.get(EXPERIMENTS, params={"filter[experiment_group_id]": group["id"]})
    assert in_group.status_code == 200
    assert {e["name"] for e in in_group.json()["data"]} == {"exp-a"}

    deleted = client.delete(f"{EXPERIMENTS}/exp-a")
    assert deleted.status_code == 204
    missing = client.get(f"{EXPERIMENTS}/exp-a")
    assert missing.status_code == 404


def test_experiment_filter_by_agent_and_dataset_version(client: TestClient) -> None:
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-v1", agent_version="1.0.0", dataset_version="v1"),
    )
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-v2", agent_version="2.0.0", dataset_version="v1"),
    )
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-v3", agent_version="2.0.0", dataset_version="v2"),
    )

    by_agent_version = client.get(EXPERIMENTS, params={"filter[agent_version]": "2.0.0"})
    assert by_agent_version.status_code == 200
    assert {e["name"] for e in by_agent_version.json()["data"]} == {"exp-v2", "exp-v3"}

    by_dataset_version = client.get(EXPERIMENTS, params={"filter[dataset_version]": "v1"})
    assert by_dataset_version.status_code == 200
    assert {e["name"] for e in by_dataset_version.json()["data"]} == {"exp-v1", "exp-v2"}

    combined = client.get(
        EXPERIMENTS,
        params={"filter[agent_version]": "2.0.0", "filter[dataset_version]": "v2"},
    )
    assert combined.status_code == 200
    assert {e["name"] for e in combined.json()["data"]} == {"exp-v3"}


def test_experiment_filter_by_created_at_range(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    before_create = datetime.now(timezone.utc) - timedelta(seconds=2)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-recent"))
    after_create = datetime.now(timezone.utc) + timedelta(seconds=2)

    # Range that brackets the create timestamp -> the experiment is included.
    in_range = client.get(
        EXPERIMENTS,
        params={
            "filter[name]": "exp-recent",
            "filter[created_at][$gte]": before_create.isoformat(),
            "filter[created_at][$lte]": after_create.isoformat(),
        },
    )
    assert in_range.status_code == 200, in_range.text
    assert {e["name"] for e in in_range.json()["data"]} == {"exp-recent"}

    # Range entirely after the create timestamp -> excluded.
    future_only = client.get(
        EXPERIMENTS,
        params={
            "filter[name]": "exp-recent",
            "filter[created_at][$gte]": (after_create + timedelta(hours=1)).isoformat(),
        },
    )
    assert future_only.status_code == 200, future_only.text
    assert future_only.json()["data"] == []


def test_experiment_filter_by_created_by(client: TestClient) -> None:
    # The test harness doesn't set an authenticated principal, so we only verify the filter
    # parameter is accepted and routed through the entity store without erroring.
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-cb"))
    response = client.get(EXPERIMENTS, params={"filter[created_by]": "someone@example.com"})
    assert response.status_code == 200, response.text
