# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace summary read API tests."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient


def test_traces_read_returns_core_trace_summary(client: TestClient, make_otlp_request):
    base_ns = int(datetime.now(timezone.utc).replace(microsecond=0).timestamp() * 1_000_000_000)
    body = make_otlp_request(
        [
            {
                "name": "root-agent",
                "span_id": "0000000000000001",
                "start_time_unix_nano": base_ns,
                "end_time_unix_nano": base_ns + 100_000_000,
                "attributes": {
                    "openinference.span.kind": "AGENT",
                    "gen_ai.conversation.id": "trace-session",
                    "project": "project-a",
                    "experiment.run_id": "run-a",
                    "dataset.name": "dataset-a",
                    "experiment.metadata": {"split": "dev"},
                    "deployment.environment.name": "prod",
                    "tag.tags": ["trace-read"],
                    "metadata": {"owner": "trace-test"},
                    "input.value": '{"task":"solve"}',
                    "output.value": '{"answer":"done"}',
                },
            },
            {
                "name": "llm-call",
                "span_id": "0000000000000002",
                "parent_span_id": "0000000000000001",
                "start_time_unix_nano": base_ns + 1_000_000_000,
                "end_time_unix_nano": base_ns + 1_200_000_000,
                "attributes": {
                    "openinference.span.kind": "LLM",
                    "gen_ai.conversation.id": "trace-session",
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o-mini",
                    "gen_ai.usage.input_tokens": 420,
                    "gen_ai.usage.output_tokens": 310,
                    "gen_ai.usage.cached_tokens": 128,
                    "gen_ai.usage.total_tokens": 858,
                    "llm.cost.prompt": 0.0024,
                    "llm.cost.completion": 0.0037,
                    "llm.cost.total": 0.0061,
                },
            },
        ]
    )

    ingest_response = client.post(
        "/apis/intake/v2/workspaces/default/ingest/otlp/v1/traces",
        content=body,
        headers={"Content-Type": "application/x-protobuf"},
    )
    assert ingest_response.status_code == 200, ingest_response.text

    traces_response = client.get(
        "/apis/intake/v2/workspaces/default/traces",
        params={
            "filter[session_id]": "trace-session",
            "filter[evaluation_run_id]": "run-a",
            "page_size": 20,
        },
    )
    assert traces_response.status_code == 200, traces_response.text
    payload = traces_response.json()
    assert payload["pagination"]["total_results"] == 1
    trace = payload["data"][0]
    assert trace["id"] == "00000000000000000000000000000001"
    assert trace["session_id"] == "trace-session"
    assert trace["workspace"] == "default"
    assert trace["root_span_id"] == "0000000000000001"
    assert trace["name"] == "root-agent"
    assert trace["status"] == "success"
    assert trace["input_tokens"] == 420
    assert trace["output_tokens"] == 310
    assert trace["cached_tokens"] == 128
    assert trace["total_tokens"] == 858
    assert Decimal(str(trace["cost_usd"])) == Decimal("0.0061")
    assert Decimal(str(trace["cost_input_usd"])) == Decimal("0.0024")
    assert Decimal(str(trace["cost_output_usd"])) == Decimal("0.0037")
    assert trace["span_count"] == 2
    assert trace["error_count"] == 0
    assert trace["evaluation_context"]["evaluation_run_id"] == "run-a"
    assert trace["evaluation_context"]["dataset_name"] == "dataset-a"
    assert trace["evaluation_context"]["metadata"] == {"split": "dev"}
    assert "source_format" not in trace
    assert "input" not in trace
    assert "output" not in trace
    assert "project" not in trace
    assert "models" not in trace

    get_response = client.get(f"/apis/intake/v2/workspaces/default/traces/{trace['id']}")
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["id"] == trace["id"]

    summary_response = client.get(
        "/apis/intake/v2/workspaces/default/traces",
        params={"filter[session_id]": "trace-session", "mode": "summary", "page_size": 20},
    )
    assert summary_response.status_code == 200, summary_response.text
    summary_trace = summary_response.json()["data"][0]
    assert summary_trace["id"] == trace["id"]
    assert summary_trace["status"] == "success"
    assert summary_trace["evaluation_context"]["evaluation_run_id"] == "run-a"
    assert "input_tokens" not in summary_trace
    assert "cost_usd" not in summary_trace
    assert "span_count" not in summary_trace


def test_traces_read_picks_earliest_root_when_trace_has_multiple_roots(client: TestClient, make_otlp_request):
    base_ns = int(datetime.now(timezone.utc).replace(microsecond=0).timestamp() * 1_000_000_000)
    body = make_otlp_request(
        [
            {
                "name": "earliest-root",
                "span_id": "0000000000000101",
                "start_time_unix_nano": base_ns,
                "end_time_unix_nano": base_ns + 100_000_000,
                "attributes": {"gen_ai.conversation.id": "multi-root-session"},
            },
            {
                "name": "later-root",
                "span_id": "0000000000000102",
                "start_time_unix_nano": base_ns + 1_000_000_000,
                "end_time_unix_nano": base_ns + 1_100_000_000,
                "attributes": {"gen_ai.conversation.id": "multi-root-session"},
            },
        ],
        trace_id="00000000000000000000000000000101",
    )

    ingest_response = client.post(
        "/apis/intake/v2/workspaces/default/ingest/otlp/v1/traces",
        content=body,
        headers={"Content-Type": "application/x-protobuf"},
    )
    assert ingest_response.status_code == 200, ingest_response.text

    traces_response = client.get(
        "/apis/intake/v2/workspaces/default/traces",
        params={"filter[session_id]": "multi-root-session", "page_size": 20},
    )
    assert traces_response.status_code == 200, traces_response.text
    payload = traces_response.json()
    assert payload["pagination"]["total_results"] == 1
    trace = payload["data"][0]
    assert trace["id"] == "00000000000000000000000000000101"
    assert trace["name"] == "earliest-root"
    assert trace["root_span_id"] == "0000000000000101"
