# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ATIF ingest marks the touched experiment dirty on the rollup refresher.

The refresh worker's flush/write logic is covered by the unit tests in
``test_experiment_rollup_refresher.py``; here we verify the ingest-path wiring that
queues experiments for it.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi.testclient import TestClient

ATIF_INGEST = "/apis/intake/v2/workspaces/default/ingest/atif"
EXPERIMENTS = "/apis/intake/v2/workspaces/default/experiments"
GROUPS = "/apis/intake/v2/workspaces/default/experiment-groups"


def _ensure_group(client: TestClient, name: str = "metrics-refresh-group") -> str:
    response = client.post(GROUPS, json={"name": name})
    if response.status_code == 409:
        response = client.get(f"{GROUPS}/{name}")
    response.raise_for_status()
    return response.json()["id"]


def _service(client: TestClient) -> Any:
    # client.app is a FastAPI app at runtime but typed as a bare ASGI callable.
    state = cast(Any, client.app).state
    return getattr(state, "intake_service", None) or getattr(state, "service", None)


def _atif_body(*, experiment_id: str, score: float) -> dict[str, Any]:
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": f"{experiment_id}-session",
        "experiment_context": {"experiment_id": experiment_id, "test_case_id": "case-1"},
        "extra": {"task_name": "case-1", "verifier_result": {"rewards": {"reward": score}}},
        "agent": {"name": "sample-agent", "version": "1.0.0", "model_name": "provider/sample-model"},
        "steps": [],
    }


def test_atif_ingest_marks_experiment_dirty(client: TestClient) -> None:
    group_id = _ensure_group(client)
    experiment_id = "metrics-dirty-exp"
    created = client.post(
        EXPERIMENTS,
        json={"name": experiment_id, "experiment_group_id": group_id, "dataset_name": "ds"},
    )
    assert created.status_code == 201, created.text

    response = client.post(ATIF_INGEST, json=_atif_body(experiment_id=experiment_id, score=1.0))
    assert response.status_code == 201, response.text

    refresher = _service(client).rollup_refresher
    assert refresher is not None
    assert ("default", experiment_id) in refresher.pending()


def test_atif_ingest_without_experiment_context_marks_nothing(client: TestClient) -> None:
    response = client.post(
        ATIF_INGEST,
        json={
            "schema_version": "ATIF-v1.6",
            "session_id": "no-context-session",
            "extra": {"verifier_result": {"rewards": {"reward": 1.0}}},
            "agent": {"name": "sample-agent", "version": "1.0.0"},
            "steps": [],
        },
    )
    assert response.status_code == 201, response.text

    refresher = _service(client).rollup_refresher
    assert refresher is not None
    assert refresher.pending() == set()
