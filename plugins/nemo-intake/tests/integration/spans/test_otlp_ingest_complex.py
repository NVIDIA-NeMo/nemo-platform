# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Complex OTLP parent-child ingest tests."""

from fastapi.testclient import TestClient


def test_otlp_ingest_parent_child_tree(client: TestClient, make_otlp_request):
    body = make_otlp_request(
        [
            {
                "name": "chain",
                "span_id": "0000000000000001",
                "attributes": {
                    "openinference.span.kind": "CHAIN",
                    "gen_ai.conversation.id": "conv-complex",
                },
            },
            {
                "name": "tool",
                "span_id": "0000000000000002",
                "parent_span_id": "0000000000000001",
                "attributes": {
                    "openinference.span.kind": "TOOL",
                    "gen_ai.conversation.id": "conv-complex",
                    "tool.name": "search",
                },
            },
            {
                "name": "llm",
                "span_id": "0000000000000003",
                "parent_span_id": "0000000000000002",
                "attributes": {
                    "openinference.span.kind": "LLM",
                    "gen_ai.conversation.id": "conv-complex",
                    "gen_ai.response.model": "model-c",
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

    spans_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[session_id]": "conv-complex", "page_size": 20, "sort": "started_at"},
    )
    assert spans_response.status_code == 200, spans_response.text
    spans_by_name = {span["name"]: span for span in spans_response.json()["data"]}
    assert set(spans_by_name) == {"chain", "tool", "llm"}
    assert spans_by_name["chain"]["kind"] == "CHAIN"
    assert spans_by_name["chain"].get("parent_span_id") is None
    assert spans_by_name["tool"]["kind"] == "TOOL"
    assert spans_by_name["tool"]["parent_span_id"] == spans_by_name["chain"]["span_id"]
    assert spans_by_name["tool"]["tool_name"] == "search"
    assert spans_by_name["llm"]["kind"] == "LLM"
    assert spans_by_name["llm"]["parent_span_id"] == spans_by_name["tool"]["span_id"]
    assert {span["session_id"] for span in spans_by_name.values()} == {"conv-complex"}
