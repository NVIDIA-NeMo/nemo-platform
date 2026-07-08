# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse schema bootstrap tests."""

from fastapi.testclient import TestClient
from nemo_intake_plugin.spans.clickhouse_client import ClickHouseSpanClient, bootstrap_schema, get_intake_runtime


def test_clickhouse_bootstrap_is_idempotent(clickhouse_client: ClickHouseSpanClient, run_async):
    run_async(bootstrap_schema(clickhouse_client))
    run_async(bootstrap_schema(clickhouse_client))

    result = run_async(
        clickhouse_client.query(
            f"SELECT version_num FROM {clickhouse_client.table('clickhouse_alembic_version')} FINAL"
            " ORDER BY version_num"
        )
    )
    assert result.result_rows == [
        ("ch_annotations_0001",),
        ("ch_evaluator_results_0001",),
        ("ch_evaluator_results_0002",),
        ("ch_spans_0002",),
        ("ch_trace_index_0003",),
        ("ch_trace_index_0004_nemo_keys",),
    ]


def test_intake_startup_does_not_bootstrap_clickhouse(client: TestClient):
    clickhouse_client = get_intake_runtime().clickhouse_client
    assert clickhouse_client is not None
    assert clickhouse_client._bootstrapped is False

    response = client.get("/apis/intake/v2/workspaces/default/spans")

    assert response.status_code == 200, response.text
    assert clickhouse_client._bootstrapped is True
