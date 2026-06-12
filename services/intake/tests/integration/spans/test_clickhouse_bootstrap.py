# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse schema bootstrap tests."""

from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.intake.service import IntakeService
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient, bootstrap_schema


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


def test_intake_service_readiness_does_not_bootstrap_service_owned_clickhouse(client: TestClient, run_async):
    app = cast(FastAPI, client.app)
    service = cast(IntakeService, app.state.intake_service)

    assert service.clickhouse_client is not None
    assert run_async(service.is_ready()) is True
    assert service.clickhouse_client._bootstrapped is False

    response = client.get("/apis/intake/v2/workspaces/default/spans")

    assert response.status_code == 200, response.text
    assert service.clickhouse_client._bootstrapped is True
