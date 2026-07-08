# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ATIF ingest writes evaluator_results rows for Harbor verifier_result blocks."""

from __future__ import annotations

from fastapi.testclient import TestClient

ATIF_INGEST = "/apis/intake/v2/workspaces/default/ingest/atif"
EVAL_BASE = "/apis/intake/v2/workspaces/default/evaluator-results"


def test_atif_ingest_extracts_verifier_reward_into_evaluator_results(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-eval-session",
        "extra": {
            "task_name": "eval-task",
            "verifier": {
                "started_at": "2026-05-04T19:01:01.657282Z",
                "finished_at": "2026-05-04T19:06:45.570079Z",
            },
            "verifier_result": {"rewards": {"reward": 0.42}},
        },
        "agent": {"name": "agent-x", "version": "1.0"},
        "steps": [],
    }
    response = client.post(ATIF_INGEST, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(EVAL_BASE, params={"page_size": 50})
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    # 1D reward convention -> named by its key, "reward" (not the old hardcoded "harbor.verifier").
    assert row["name"] == "reward"
    assert row["data_type"] == "NUMERIC"
    assert row["value"] == 0.42
    assert row["session_id"] == "atif-eval-session"
    assert row["created_by"] == "intake:atif_importer"


def test_atif_ingest_emits_one_row_per_reward_key(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-multi-criterion",
        "extra": {
            "task_name": "eval-task",
            "verifier_result": {"rewards": {"correctness": 0.75, "structure": 1.0, "v1/quality": 0.5}},
        },
        "agent": {"name": "agent-x", "version": "1.0"},
        "steps": [],
    }
    response = client.post(ATIF_INGEST, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(EVAL_BASE, params={"page_size": 50})
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    # One row per reward key; namespaced keys (v1/quality) pass through verbatim.
    assert {row["name"]: row["value"] for row in rows} == {
        "correctness": 0.75,
        "structure": 1.0,
        "v1/quality": 0.5,
    }


def test_atif_re_ingest_dedupes_per_reward(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-reingest",
        "extra": {
            "task_name": "eval-task",
            "verifier_result": {"rewards": {"correctness": 0.75, "structure": 1.0}},
        },
        "agent": {"name": "agent-x", "version": "1.0"},
        "steps": [],
    }
    assert client.post(ATIF_INGEST, json=body).status_code == 201, "first ingest"
    assert client.post(ATIF_INGEST, json=body).status_code == 201, "identical re-ingest"

    listed = client.get(EVAL_BASE, params={"page_size": 50})
    # Deterministic per-(span, key) ids -> identical re-ingest dedupes, no doubling.
    assert listed.json()["pagination"]["total_results"] == 2
    assert {row["name"] for row in listed.json()["data"]} == {"correctness", "structure"}


def test_atif_ingest_falls_back_to_reward_for_bare_score(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-bare-score",
        "extra": {"task_name": "eval-task", "verifier_result": {"score": 0.9}},
        "agent": {"name": "agent-x", "version": "1.0"},
        "steps": [],
    }
    response = client.post(ATIF_INGEST, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(EVAL_BASE, params={"page_size": 50})
    rows = listed.json()["data"]
    assert len(rows) == 1
    assert rows[0]["name"] == "reward"
    assert rows[0]["value"] == 0.9


def test_atif_ingest_without_verifier_result_writes_no_evaluator_results(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-no-eval",
        "agent": {"name": "agent-x", "version": "1.0"},
        "steps": [],
    }
    response = client.post(ATIF_INGEST, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(EVAL_BASE)
    assert listed.status_code == 200, listed.text
    assert listed.json()["pagination"]["total_results"] == 0
