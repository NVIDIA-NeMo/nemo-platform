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


def _experiment_body(*, experiment_group_id: str, **overrides: Any) -> dict:
    body = {
        "name": "terminal-bench-2_claude-code_opus_baseline",
        "experiment_group_id": experiment_group_id,
        "dataset_name": "terminal-bench-2",
        "dataset_version": "v1",
        "source_link": "https://example.com/experiments/tb2-baseline",
        "metadata": {"job_name": "tb2-baseline"},
    }
    body.update(overrides)
    return body


def _create_group(client: TestClient, name: str = "default-test-group") -> dict:
    """Create or fetch an experiment group; returns the JSON body."""
    response = client.post(GROUPS, json={"name": name})
    if response.status_code == 409:
        response = client.get(f"{GROUPS}/{name}")
    response.raise_for_status()
    return response.json()


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


def test_experiment_update_moves_between_groups_and_edits(client: TestClient) -> None:
    group_a = client.post(GROUPS, json={"name": "grp-a"}).json()
    group_b = client.post(GROUPS, json={"name": "grp-b"}).json()
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-a", experiment_group_id=group_a["id"]))

    # Move the experiment from group_a to group_b and edit its description.
    body = _experiment_body(name="exp-a", experiment_group_id=group_b["id"], description="looks good")
    updated = client.put(f"{EXPERIMENTS}/exp-a", json=body)
    assert updated.status_code == 200, updated.text
    assert updated.json()["experiment_group_id"] == group_b["id"]
    assert updated.json()["description"] == "looks good"


def test_experiment_update_rejects_immutable_change(client: TestClient) -> None:
    group = _create_group(client)
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-a", dataset_name="tb2", experiment_group_id=group["id"]),
    )
    changed = _experiment_body(name="exp-a", dataset_name="tb3", experiment_group_id=group["id"])
    resp = client.put(f"{EXPERIMENTS}/exp-a", json=changed)
    assert resp.status_code == 409, resp.text
    assert "dataset_name" in resp.json()["detail"]
    missing = client.put(
        f"{EXPERIMENTS}/missing",
        json=_experiment_body(name="missing", experiment_group_id=group["id"]),
    )
    assert missing.status_code == 404


def test_experiment_crud_and_empty_rollups(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "grp"}).json()

    created = client.post(EXPERIMENTS, json=_experiment_body(experiment_group_id=group["id"]))
    assert created.status_code == 201, created.text
    exp = created.json()
    assert exp["name"] == "terminal-bench-2_claude-code_opus_baseline"
    assert exp["experiment_group_id"] == group["id"]
    assert exp["dataset_name"] == "terminal-bench-2"
    assert exp["source_link"] == "https://example.com/experiments/tb2-baseline"
    assert exp["metadata"] == {"job_name": "tb2-baseline"}

    # Rollups exist on the read model but are empty until ClickHouse hydration lands.
    assert exp["evaluator_names"] == []
    assert exp["model_names"] == []
    assert exp["agent_names"] == []
    assert exp["agent_versions"] == []
    assert exp["aggregate_scores"] is None
    assert exp["run_count"] == 0


def test_experiment_read_degrades_when_rollup_hydration_fails(client: TestClient) -> None:
    class FailingRollupRepository:
        async def get_rollups(self, *, workspace: str, experiment_ids: list[str]) -> dict:
            raise RuntimeError("clickhouse unavailable")

    group = _create_group(client)
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_experiment_rollup_repository] = lambda: FailingRollupRepository()
    try:
        created = client.post(
            EXPERIMENTS,
            json=_experiment_body(name="exp-rollup-fails", experiment_group_id=group["id"]),
        )
        assert created.status_code == 201, created.text

        fetched = client.get(f"{EXPERIMENTS}/exp-rollup-fails")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["name"] == "exp-rollup-fails"
        assert fetched.json()["run_count"] == 0
        assert fetched.json()["aggregate_scores"] is None
    finally:
        app.dependency_overrides.pop(get_experiment_rollup_repository, None)


def test_experiment_create_rejects_missing_group_id(client: TestClient) -> None:
    body = _experiment_body(name="exp-no-group", experiment_group_id="placeholder")
    body.pop("experiment_group_id")
    response = client.post(EXPERIMENTS, json=body)
    assert response.status_code == 422, response.text


def test_experiment_create_rejects_unknown_group_id(client: TestClient) -> None:
    response = client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-bad-group", experiment_group_id="experiment_group-does-not-exist"),
    )
    assert response.status_code == 400, response.text
    assert "must be created before" in response.json()["detail"]


def test_delete_group_cascades_to_experiments(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "doomed-group"}).json()
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-doomed-1", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-doomed-2", experiment_group_id=group["id"]))

    deleted = client.delete(f"{GROUPS}/doomed-group")
    assert deleted.status_code == 204, deleted.text

    # Both child experiments are gone with the group.
    for child_name in ("exp-doomed-1", "exp-doomed-2"):
        missing = client.get(f"{EXPERIMENTS}/{child_name}")
        assert missing.status_code == 404


def test_experiment_conflict_and_not_found(client: TestClient) -> None:
    group = _create_group(client)
    created = client.post(EXPERIMENTS, json=_experiment_body(experiment_group_id=group["id"]))
    assert created.status_code == 201
    duplicate = client.post(EXPERIMENTS, json=_experiment_body(experiment_group_id=group["id"]))
    assert duplicate.status_code == 409
    missing = client.get(f"{EXPERIMENTS}/does-not-exist")
    assert missing.status_code == 404
    missing_delete = client.delete(f"{EXPERIMENTS}/does-not-exist")
    assert missing_delete.status_code == 404


def test_experiment_list_and_scope_to_group(client: TestClient) -> None:
    group_a = client.post(GROUPS, json={"name": "grp-a"}).json()
    group_b = client.post(GROUPS, json={"name": "grp-b"}).json()
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-a", experiment_group_id=group_a["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-b", experiment_group_id=group_b["id"]))

    all_resp = client.get(EXPERIMENTS)
    assert all_resp.status_code == 200
    names = {e["name"] for e in all_resp.json()["data"]}
    assert {"exp-a", "exp-b"} <= names

    in_group_a = client.get(EXPERIMENTS, params={"filter[experiment_group_id]": group_a["id"]})
    assert in_group_a.status_code == 200
    assert {e["name"] for e in in_group_a.json()["data"]} == {"exp-a"}

    deleted = client.delete(f"{EXPERIMENTS}/exp-a")
    assert deleted.status_code == 204
    missing = client.get(f"{EXPERIMENTS}/exp-a")
    assert missing.status_code == 404


def test_experiment_filter_by_dataset_version(client: TestClient) -> None:
    group = _create_group(client)
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-v1", dataset_version="v1", experiment_group_id=group["id"]),
    )
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-v2", dataset_version="v1", experiment_group_id=group["id"]),
    )
    client.post(
        EXPERIMENTS,
        json=_experiment_body(name="exp-v3", dataset_version="v2", experiment_group_id=group["id"]),
    )

    by_dataset_version = client.get(EXPERIMENTS, params={"filter[dataset_version]": "v1"})
    assert by_dataset_version.status_code == 200
    assert {e["name"] for e in by_dataset_version.json()["data"]} == {"exp-v1", "exp-v2"}


def test_experiment_filter_by_created_at_range(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    group = _create_group(client)
    before_create = datetime.now(timezone.utc) - timedelta(seconds=2)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-recent", experiment_group_id=group["id"]))
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
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-cb", experiment_group_id=group["id"]))
    response = client.get(EXPERIMENTS, params={"filter[created_by]": "someone@example.com"})
    assert response.status_code == 200, response.text


def test_soft_delete_frees_name_for_reuse(client: TestClient) -> None:
    group = _create_group(client)
    first = client.post(EXPERIMENTS, json=_experiment_body(name="reusable", experiment_group_id=group["id"]))
    assert first.status_code == 201, first.text

    deleted = client.delete(f"{EXPERIMENTS}/reusable")
    assert deleted.status_code == 204, deleted.text

    # The original name is now free; a new experiment can claim it.
    second = client.post(EXPERIMENTS, json=_experiment_body(name="reusable", experiment_group_id=group["id"]))
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]


def test_list_hides_soft_deleted_by_default(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-live", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-gone", experiment_group_id=group["id"]))
    client.delete(f"{EXPERIMENTS}/exp-gone")

    listed = client.get(EXPERIMENTS)
    assert listed.status_code == 200
    names = {e["name"] for e in listed.json()["data"]}
    assert "exp-live" in names
    assert "exp-gone" not in names
    assert not any(name.startswith("exp-gone-deleted-") for name in names)


def test_filter_is_deleted_true_returns_only_deleted(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-still-here", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-trash", experiment_group_id=group["id"]))
    client.delete(f"{EXPERIMENTS}/exp-trash")

    response = client.get(EXPERIMENTS, params={"filter[is_deleted]": "true"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # Live experiments are excluded; only deleted rows (with mangled names) appear. The
    # response body intentionally omits ``is_deleted``; the filter context and mangled name
    # are the signal that these are trash-bin rows.
    assert any(e["name"].startswith("exp-trash-deleted-") for e in data)
    assert not any(e["name"] == "exp-still-here" for e in data)


def test_group_soft_delete_cascades_and_frees_names(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "doomed-group-v2"}).json()
    client.post(EXPERIMENTS, json=_experiment_body(name="child-1", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="child-2", experiment_group_id=group["id"]))

    deleted = client.delete(f"{GROUPS}/doomed-group-v2")
    assert deleted.status_code == 204, deleted.text

    # Group and children all read as 404 (live view).
    assert client.get(f"{GROUPS}/doomed-group-v2").status_code == 404
    for child_name in ("child-1", "child-2"):
        assert client.get(f"{EXPERIMENTS}/{child_name}").status_code == 404

    # Names are reusable in a fresh group.
    fresh_group = client.post(GROUPS, json={"name": "doomed-group-v2"})
    assert fresh_group.status_code == 201, fresh_group.text
    revived = client.post(
        EXPERIMENTS, json=_experiment_body(name="child-1", experiment_group_id=fresh_group.json()["id"])
    )
    assert revived.status_code == 201, revived.text

    # Trash view still surfaces the cascaded rows.
    deleted_groups = client.get(GROUPS, params={"filter[is_deleted]": "true"})
    assert any(g["name"].startswith("doomed-group-v2-deleted-") for g in deleted_groups.json()["data"])
    deleted_exps = client.get(EXPERIMENTS, params={"filter[is_deleted]": "true"})
    deleted_names = {e["name"] for e in deleted_exps.json()["data"]}
    assert any(n.startswith("child-1-deleted-") for n in deleted_names)
    assert any(n.startswith("child-2-deleted-") for n in deleted_names)


def test_create_experiment_in_deleted_group_rejected(client: TestClient) -> None:
    group = client.post(GROUPS, json={"name": "ephemeral-group"}).json()
    client.delete(f"{GROUPS}/ephemeral-group")

    response = client.post(
        EXPERIMENTS,
        json=_experiment_body(name="orphan", experiment_group_id=group["id"]),
    )
    assert response.status_code == 400, response.text
    assert "deleted" in response.json()["detail"].lower()


def test_update_or_delete_deleted_experiment_returns_404(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-once", experiment_group_id=group["id"]))
    client.delete(f"{EXPERIMENTS}/exp-once")

    # GET, PUT, and a second DELETE all 404 on the (now-renamed) deleted row.
    assert client.get(f"{EXPERIMENTS}/exp-once").status_code == 404
    assert (
        client.put(
            f"{EXPERIMENTS}/exp-once",
            json=_experiment_body(name="exp-once", experiment_group_id=group["id"]),
        ).status_code
        == 404
    )
    delete_response = client.delete(f"{EXPERIMENTS}/exp-once")
    assert delete_response.status_code == 404


def test_pin_and_unpin_experiment(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-pin", experiment_group_id=group["id"]))

    # New experiments start unpinned.
    fetched = client.get(f"{EXPERIMENTS}/exp-pin")
    assert fetched.status_code == 200
    assert fetched.json()["pinned_at"] is None

    # Pin sets pinned_at to a timestamp.
    pinned = client.post(f"{EXPERIMENTS}/exp-pin/pin")
    assert pinned.status_code == 200, pinned.text
    first_pinned_at = pinned.json()["pinned_at"]
    assert first_pinned_at is not None

    # Re-pinning refreshes pinned_at (most-recently-pinned-first ordering).
    re_pinned = client.post(f"{EXPERIMENTS}/exp-pin/pin")
    assert re_pinned.status_code == 200, re_pinned.text
    assert re_pinned.json()["pinned_at"] >= first_pinned_at

    # Unpin clears pinned_at.
    unpinned = client.delete(f"{EXPERIMENTS}/exp-pin/pin")
    assert unpinned.status_code == 200, unpinned.text
    assert unpinned.json()["pinned_at"] is None

    # Unpin on an already-unpinned experiment is a no-op.
    again = client.delete(f"{EXPERIMENTS}/exp-pin/pin")
    assert again.status_code == 200, again.text
    assert again.json()["pinned_at"] is None


def test_pin_unknown_experiment_returns_404(client: TestClient) -> None:
    assert client.post(f"{EXPERIMENTS}/missing/pin").status_code == 404
    assert client.delete(f"{EXPERIMENTS}/missing/pin").status_code == 404


def test_pin_rejects_deleted_experiment(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-soft", experiment_group_id=group["id"]))
    assert client.delete(f"{EXPERIMENTS}/exp-soft").status_code == 204
    assert client.post(f"{EXPERIMENTS}/exp-soft/pin").status_code == 404


def test_filter_by_is_pinned(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-pinned-a", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-pinned-b", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-not-pinned", experiment_group_id=group["id"]))
    client.post(f"{EXPERIMENTS}/exp-pinned-a/pin")
    client.post(f"{EXPERIMENTS}/exp-pinned-b/pin")

    only_pinned = client.get(EXPERIMENTS, params={"filter[is_pinned]": "true"})
    assert only_pinned.status_code == 200, only_pinned.text
    pinned_names = {e["name"] for e in only_pinned.json()["data"]}
    assert pinned_names == {"exp-pinned-a", "exp-pinned-b"}

    only_unpinned = client.get(EXPERIMENTS, params={"filter[is_pinned]": "false"})
    assert only_unpinned.status_code == 200, only_unpinned.text
    unpinned_names = {e["name"] for e in only_unpinned.json()["data"]}
    assert "exp-not-pinned" in unpinned_names
    assert "exp-pinned-a" not in unpinned_names
    assert "exp-pinned-b" not in unpinned_names

    no_filter = client.get(EXPERIMENTS)
    all_names = {e["name"] for e in no_filter.json()["data"]}
    assert {"exp-pinned-a", "exp-pinned-b", "exp-not-pinned"} <= all_names


def test_sort_by_pinned_at_most_recent_first(client: TestClient) -> None:
    group = _create_group(client)
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-old-pin", experiment_group_id=group["id"]))
    client.post(EXPERIMENTS, json=_experiment_body(name="exp-new-pin", experiment_group_id=group["id"]))
    client.post(f"{EXPERIMENTS}/exp-old-pin/pin")
    client.post(f"{EXPERIMENTS}/exp-new-pin/pin")

    pinned_desc = client.get(EXPERIMENTS, params={"filter[is_pinned]": "true", "sort": "-pinned_at"})
    assert pinned_desc.status_code == 200, pinned_desc.text
    names_desc = [e["name"] for e in pinned_desc.json()["data"]]
    assert names_desc.index("exp-new-pin") < names_desc.index("exp-old-pin")

    pinned_asc = client.get(EXPERIMENTS, params={"filter[is_pinned]": "true", "sort": "pinned_at"})
    assert pinned_asc.status_code == 200, pinned_asc.text
    names_asc = [e["name"] for e in pinned_asc.json()["data"]]
    assert names_asc.index("exp-old-pin") < names_asc.index("exp-new-pin")
