# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OTLP message payload preservation tests."""

import json

from fastapi.testclient import TestClient


def test_otlp_ingest_preserves_message_payloads(client: TestClient, make_otlp_request):
    input_payload = {
        "messages": [
            {"role": "system", "content": "You are terse."},
            {
                "role": "user",
                "content": "Use the weather tool.",
                "tool_calls": [
                    {"id": "call-1", "type": "function", "function": {"name": "weather", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": '{"temp":72,"unit":"f"}'},
        ],
        "embedded": {"json": {"array": [1, 2, {"deep": True}]}},
    }
    output_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "It is 72 F.",
                    "metadata": {"citations": [{"source": "tool", "id": "call-1"}]},
                }
            }
        ]
    }
    input_text = json.dumps(input_payload, separators=(",", ":"), sort_keys=True)
    output_text = json.dumps(output_payload, separators=(",", ":"), sort_keys=True)
    body = make_otlp_request(
        [
            {
                "name": "message-span",
                "attributes": {
                    "openinference.span.kind": "LLM",
                    "gen_ai.conversation.id": "conv-messages",
                    "input.value": input_text,
                    "output.value": output_text,
                },
            }
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
        params={"filter[session_id]": "conv-messages"},
    )
    assert spans_response.status_code == 200, spans_response.text
    span = spans_response.json()["data"][0]
    assert span["input"] == input_text
    assert span["output"] == output_text
    assert json.loads(span["input"]) == input_payload
    assert json.loads(span["output"]) == output_payload
