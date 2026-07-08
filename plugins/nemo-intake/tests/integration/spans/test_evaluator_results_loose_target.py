# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify the loose-target policy: writes succeed before the target span exists."""

from __future__ import annotations

from fastapi.testclient import TestClient

EVAL_BASE = "/apis/intake/v2/workspaces/default/evaluator-results"
SPANS_BASE = "/apis/intake/v2/workspaces/default/spans"


def test_evaluator_result_accepts_unknown_span_id(client: TestClient):
    response = client.post(
        EVAL_BASE,
        json={
            "span_id": "span-not-yet-ingested",
            "session_id": "session-future",
            "name": "faithfulness",
            "value": 0.42,
            "data_type": "NUMERIC",
        },
    )
    assert response.status_code == 201, response.text
    eval_payload = response.json()
    assert eval_payload["span_id"] == "span-not-yet-ingested"

    listed = client.get(f"{SPANS_BASE}/span-not-yet-ingested/evaluator-results")
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["evaluator_result_id"] == eval_payload["evaluator_result_id"]


def test_multiple_evaluator_results_for_one_span(client: TestClient):
    span_id = "span-multi-metric"
    for name, value in [("faithfulness", 0.9), ("relevance", 0.6), ("helpfulness", 0.75)]:
        response = client.post(
            EVAL_BASE,
            json={
                "span_id": span_id,
                "session_id": "session-multi",
                "name": name,
                "value": value,
                "data_type": "NUMERIC",
            },
        )
        assert response.status_code == 201, response.text

    listed = client.get(f"{SPANS_BASE}/{span_id}/evaluator-results")
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert {row["name"] for row in rows} == {"faithfulness", "relevance", "helpfulness"}
