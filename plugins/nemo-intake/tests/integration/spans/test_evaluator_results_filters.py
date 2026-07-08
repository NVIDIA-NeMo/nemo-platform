# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Filter tests for the evaluator_results list endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

EVAL_BASE = "/apis/intake/v2/workspaces/default/evaluator-results"


def _seed(client: TestClient) -> None:
    rows = [
        {
            "span_id": "span-a",
            "session_id": "session-1",
            "name": "faithfulness",
            "value": 0.9,
            "data_type": "NUMERIC",
        },
        {
            "span_id": "span-a",
            "session_id": "session-1",
            "name": "relevance",
            "value": 0.4,
            "data_type": "NUMERIC",
        },
        {
            "span_id": "span-b",
            "session_id": "session-1",
            "name": "faithfulness",
            "value": 0.2,
            "data_type": "NUMERIC",
        },
        {
            "span_id": "span-c",
            "session_id": "session-2",
            "name": "label",
            "string_value": "good",
            "data_type": "CATEGORICAL",
        },
    ]
    for row in rows:
        response = client.post(EVAL_BASE, json=row)
        assert response.status_code == 201, response.text


def test_filter_by_name(client: TestClient):
    _seed(client)
    response = client.get(EVAL_BASE, params={"filter[name]": "faithfulness", "page_size": 50})
    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()["data"]}
    assert names == {"faithfulness"}


def test_filter_by_span_id(client: TestClient):
    _seed(client)
    response = client.get(EVAL_BASE, params={"filter[span_id]": "span-a", "page_size": 50})
    assert response.status_code == 200, response.text
    span_ids = {row["span_id"] for row in response.json()["data"]}
    assert span_ids == {"span-a"}


def test_filter_by_session_id(client: TestClient):
    _seed(client)
    response = client.get(EVAL_BASE, params={"filter[session_id]": "session-1", "page_size": 50})
    assert response.status_code == 200, response.text
    sessions = {row["session_id"] for row in response.json()["data"]}
    assert sessions == {"session-1"}


def test_filter_by_data_type(client: TestClient):
    _seed(client)
    response = client.get(EVAL_BASE, params={"filter[data_type]": "CATEGORICAL", "page_size": 50})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["string_value"] == "good"


def test_filter_value_range(client: TestClient):
    _seed(client)
    response = client.get(
        EVAL_BASE,
        params={"filter[value][$lte]": "0.5", "page_size": 50, "sort": "value"},
    )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert [row["name"] for row in rows] == ["faithfulness", "relevance"]
    assert rows[0]["value"] == 0.2


def test_filter_rejects_unknown_field(client: TestClient):
    _seed(client)
    response = client.get(EVAL_BASE, params={"filter[unsupported]": "x"})
    assert response.status_code in (400, 422), response.text
