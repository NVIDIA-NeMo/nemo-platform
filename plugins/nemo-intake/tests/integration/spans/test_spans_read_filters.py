# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Span read filter tests."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient


def test_spans_read_filters(client: TestClient, make_otlp_request):
    base_ns = int(datetime.now(timezone.utc).replace(microsecond=0).timestamp() * 1_000_000_000)
    specs = []
    shapes = [
        ("conv-a", "LLM", "model-a", None, False),
        ("conv-a", "TOOL", None, "search", False),
        ("conv-a", "AGENT", None, None, False),
        ("conv-a", "LLM", "model-b", None, False),
        ("conv-a", "TOOL", None, "calculator", True),
        ("conv-b", "LLM", "model-a", None, False),
        ("conv-b", "TOOL", None, "search", False),
        ("conv-b", "AGENT", None, None, False),
        ("conv-b", "LLM", "model-a", None, False),
        ("conv-b", "RETRIEVER", "model-b", None, False),
    ]
    for index, (session_id, kind, model, tool_name, error) in enumerate(shapes):
        attributes = {
            "openinference.span.kind": kind,
            "gen_ai.conversation.id": session_id,
        }
        if index < 3:
            attributes["project"] = "project-a"
        elif index < 6:
            attributes["project"] = "project-b"
        if model is not None:
            attributes["gen_ai.response.model"] = model
        if tool_name is not None:
            attributes["tool.name"] = tool_name
        if index in {0, 3, 5, 8}:
            attributes["gen_ai.system"] = "openai"
        if index in {0, 2}:
            attributes["gen_ai.agent.id"] = "agent-x"
        spec: dict[str, object] = {
            "name": f"span-{index}",
            "span_id": f"{index + 1:016x}",
            "start_time_unix_nano": base_ns + index * 1_000_000_000,
            "end_time_unix_nano": base_ns + index * 1_000_000_000 + 100_000_000,
            "attributes": attributes,
            "error": error,
        }
        if index == 6:
            # Make span-6 a direct child of span-5 so we can filter by parent_span_id.
            spec["parent_span_id"] = f"{6:016x}"
        specs.append(spec)

    ingest_response = client.post(
        "/apis/intake/v2/workspaces/default/ingest/otlp/v1/traces",
        content=make_otlp_request(specs),
        headers={"Content-Type": "application/x-protobuf"},
    )
    assert ingest_response.status_code == 200, ingest_response.text

    session_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[session_id]": "conv-a", "page_size": 20},
    )
    assert session_response.status_code == 200, session_response.text
    assert session_response.json()["pagination"]["total_results"] == 5
    assert {span["session_id"] for span in session_response.json()["data"]} == {"conv-a"}

    trace_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[trace_id]": "0" * 31 + "1", "page_size": 20},
    )
    assert trace_response.status_code == 200, trace_response.text
    assert trace_response.json()["pagination"]["total_results"] == 10
    assert {span["trace_id"] for span in trace_response.json()["data"]} == {"0" * 31 + "1"}

    source_format_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[source]": "otel", "page_size": 20},
    )
    assert source_format_response.status_code == 200, source_format_response.text
    assert source_format_response.json()["pagination"]["total_results"] == 10
    assert {span["source"] for span in source_format_response.json()["data"]} == {"otel"}

    project_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[project]": "project-a", "page_size": 20},
    )
    assert project_response.status_code == 200, project_response.text
    assert project_response.json()["pagination"]["total_results"] == 3
    assert {span["project"] for span in project_response.json()["data"]} == {"project-a"}

    kind_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[kind]": "LLM", "page_size": 20},
    )
    assert kind_response.status_code == 200, kind_response.text
    assert kind_response.json()["pagination"]["total_results"] == 4
    assert {span["kind"] for span in kind_response.json()["data"]} == {"LLM"}

    status_response = client.get("/apis/intake/v2/workspaces/default/spans", params={"filter[status]": "error"})
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["pagination"]["total_results"] == 1
    assert status_response.json()["data"][0]["status"] == "error"

    model_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[model]": "model-a", "page_size": 20},
    )
    assert model_response.status_code == 200, model_response.text
    assert model_response.json()["pagination"]["total_results"] == 3
    assert {span["model"] for span in model_response.json()["data"]} == {"model-a"}

    tool_response = client.get("/apis/intake/v2/workspaces/default/spans", params={"filter[tool_name]": "search"})
    assert tool_response.status_code == 200, tool_response.text
    assert tool_response.json()["pagination"]["total_results"] == 2
    assert {span["tool_name"] for span in tool_response.json()["data"]} == {"search"}

    gte = datetime.fromtimestamp((base_ns + 5 * 1_000_000_000) / 1_000_000_000, tz=timezone.utc).isoformat()
    lte = datetime.fromtimestamp((base_ns + 9 * 1_000_000_000) / 1_000_000_000, tz=timezone.utc).isoformat()
    range_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[started_at][gte]": gte,
            "filter[started_at][lte]": lte,
            "page_size": 20,
            "sort": "started_at",
        },
    )
    assert range_response.status_code == 200, range_response.text
    range_data = range_response.json()
    assert range_data["pagination"]["total_results"] == 5
    assert [span["name"] for span in range_data["data"]] == ["span-5", "span-6", "span-7", "span-8", "span-9"]

    provider_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[provider]": "openai", "page_size": 20},
    )
    assert provider_response.status_code == 200, provider_response.text
    assert provider_response.json()["pagination"]["total_results"] == 4
    assert {span["provider"] for span in provider_response.json()["data"]} == {"openai"}

    agent_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[agent_id]": "agent-x", "page_size": 20},
    )
    assert agent_response.status_code == 200, agent_response.text
    assert agent_response.json()["pagination"]["total_results"] == 2
    assert {span["agent_id"] for span in agent_response.json()["data"]} == {"agent-x"}

    parent_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[parent_span_id]": f"{6:016x}"},
    )
    assert parent_response.status_code == 200, parent_response.text
    assert parent_response.json()["pagination"]["total_results"] == 1
    assert parent_response.json()["data"][0]["name"] == "span-6"

    group_response = client.get(
        "/apis/intake/v2/workspaces/default/spans/groups",
        params={
            "by": "session_id,trace_id",
            "filter[kind]": "LLM",
            "page_size": 20,
        },
    )
    assert group_response.status_code == 200, group_response.text
    group_payload = group_response.json()
    assert group_payload["grouped_by"] == ["session_id", "trace_id"]
    assert group_payload["pagination"]["total_results"] == 2
    assert group_payload["data"] == [
        {"group": {"session_id": "conv-a", "trace_id": "0" * 31 + "1"}, "span_count": 2},
        {"group": {"session_id": "conv-b", "trace_id": "0" * 31 + "1"}, "span_count": 2},
    ]

    unsupported_response = client.get("/apis/intake/v2/workspaces/default/spans", params={"session_id": "conv-a"})
    assert unsupported_response.status_code == 400
