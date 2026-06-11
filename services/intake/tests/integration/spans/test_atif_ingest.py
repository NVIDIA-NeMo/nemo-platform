# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ATIF ingest tests."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

_HISTORICAL_GTE = "2024-01-01T00:00:00Z"


def _recent_base_time() -> datetime:
    """Return a UTC timestamp safely inside the spans list 30-day default lookback."""
    return datetime.now(timezone.utc) - timedelta(hours=2)


def _atif_timestamp(dt: datetime) -> str:
    """Format a UTC datetime the way ATIF ingest payloads expect."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{dt.microsecond:06d}Z"


def _span_started_at(dt: datetime) -> str:
    """Format a UTC datetime the way span list/get APIs return started_at."""
    return dt.replace(tzinfo=None).isoformat(timespec="microseconds")


def _span_ended_at(dt: datetime) -> str:
    return _span_started_at(dt)


def test_atif_ingest_rejects_loose_steps_payload(client: TestClient):
    body = {
        "session_id": "atif-session",
        "project": "project-a",
        "steps": [
            {"name": "plan", "started_at": "2026-01-01T00:00:00Z"},
            {
                "name": "search",
                "tool_calls": [{"name": "web_search", "arguments": {"q": "nemo"}}],
            },
            {"name": "summarize", "output": {"text": "done"}},
        ],
    }
    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 422, ingest_response.text
    error_locations = {tuple(error["loc"]) for error in ingest_response.json()["detail"]}
    assert ("body", "schema_version") in error_locations
    assert ("body", "agent") in error_locations


def test_atif_ingest_rejects_malformed_timestamps(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-bad-time",
        "agent": {"name": "test-agent", "version": "1.0"},
        "steps": [
            {"step_id": 1, "timestamp": "not-a-timestamp", "source": "user", "message": "bad timestamp"},
        ],
    }
    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 422, ingest_response.text
    errors = ingest_response.json()["detail"]
    assert errors[0]["loc"] == ["body", "steps", 0, "user", "timestamp"]
    assert "Invalid ISO 8601 timestamp" in errors[0]["msg"]


def test_atif_ingest_rejects_non_agent_tool_fields(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-non-agent-tool-fields",
        "agent": {"name": "test-agent", "version": "1.0"},
        "steps": [
            {
                "step_id": 1,
                "source": "user",
                "message": "hello",
                "tool_calls": [{"tool_call_id": "call-1", "function_name": "Bash"}],
            },
        ],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 422, ingest_response.text
    assert "tool_calls" in ingest_response.text


def test_atif_ingest_rejects_mismatched_content_parts(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-bad-content",
        "agent": {"name": "test-agent", "version": "1.0"},
        "steps": [
            {
                "step_id": 1,
                "source": "user",
                "message": [{"type": "text"}],
            },
        ],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 422, ingest_response.text
    assert "text" in ingest_response.text


def test_atif_ingest_rejects_duplicate_tool_call_ids(client: TestClient):
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-duplicate-tool-call",
        "agent": {"name": "test-agent", "version": "1.0"},
        "steps": [
            {
                "step_id": 1,
                "source": "agent",
                "tool_calls": [
                    {"tool_call_id": "call-1", "function_name": "Bash"},
                    {"tool_call_id": "call-1", "function_name": "Read"},
                ],
            },
        ],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 422, ingest_response.text
    assert "Duplicate tool_call_id 'call-1' in step 1" in ingest_response.text


@pytest.mark.parametrize(
    "schema_version",
    [
        "ATIF-v1.0",
        "ATIF-v1.1",
        "ATIF-v1.2",
        "ATIF-v1.3",
        "ATIF-v1.4",
        "ATIF-v1.5",
        "ATIF-v1.6",
        "ATIF-v1.7",
    ],
)
def test_atif_ingest_accepts_supported_schema_versions_without_rewriting(
    client: TestClient,
    schema_version: str,
):
    session_id = f"atif-{schema_version.removeprefix('ATIF-').replace('.', '-')}"
    body = {
        "schema_version": schema_version,
        "session_id": session_id,
        "agent": {"name": "test-agent", "version": "1.0"},
        "steps": [],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 201, ingest_response.text
    assert ingest_response.content == b""

    spans_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={"filter[session_id]": session_id, "page_size": 10},
    )
    assert spans_response.status_code == 200, spans_response.text
    spans = spans_response.json()["data"]
    assert len(spans) == 1
    assert spans[0]["session_id"] == session_id
    assert spans[0]["kind"] == "AGENT"
    assert spans[0]["source"] == "atif"


def test_atif_ingest_rejects_unknown_schema_version(client: TestClient):
    body = {
        "schema_version": "ATIF-v2.0",
        "session_id": "atif-unknown-version",
        "agent": {"name": "test-agent", "version": "1.0"},
        "steps": [],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 422, ingest_response.text
    assert ingest_response.json()["detail"][0]["loc"] == ["body", "schema_version"]


def test_atif_ingest_accepts_example_trajectory_and_reconstructs_read_side_data(client: TestClient):
    evaluation_run_id = "evalrun-01JZ8Q7K6V7R3X9N2M4P5A6B7C"
    evaluation_context = {
        "evaluation_id": "eval-sample-agent-baseline",
        "evaluation_sha": "abc132901",
        "evaluation_run_id": evaluation_run_id,
        "dataset_id": "sample-dataset",
        "dataset_name": "Sample Dataset",
        "dataset_version": "v1",
        "test_case_id": "sample-test-case-a",
        "metadata": {"trial": "sample-test-case-a__trial-a"},
    }
    _create_experiment(client, evaluation_context["evaluation_id"])
    base_time = _recent_base_time()
    user_step_time = base_time
    agent_step_2_time = base_time + timedelta(seconds=5, milliseconds=636)
    agent_step_3_time = base_time + timedelta(seconds=10, milliseconds=528)
    verifier_started_at = base_time + timedelta(minutes=3, seconds=1, microseconds=657282)
    verifier_finished_at = base_time + timedelta(minutes=8, seconds=45, microseconds=570079)
    another_session_step_time = user_step_time - timedelta(minutes=4, seconds=29)
    tool_call = {
        "tool_call_id": "tooluse_tuIapjh62ZTI1pildiC9sg",
        "function_name": "Bash",
        "arguments": {
            "command": "ls /app/secrets.7z",
            "description": "Check for archive availability",
        },
    }
    tool_observation = {
        "source_call_id": "tooluse_tuIapjh62ZTI1pildiC9sg",
        "content": "Exit code 1\n/app/secrets.7z\n\n[error] tool reported failure",
    }
    subagent_ref = {
        "session_id": "subagent-session-1",
        "trajectory_path": "subagents/subagent-session-1.json",
        "extra": {"agent_name": "solver"},
    }
    subagent_observation = {
        "content": "delegated solve succeeded",
        "subagent_trajectory_ref": [subagent_ref],
    }
    body = {
        "schema_version": "ATIF-v1.5",
        "session_id": "d074dfb7-3691-443c-b137-720d75e40afa",
        "evaluation_context": evaluation_context,
        "continued_trajectory_ref": "previous-session",
        "notes": "Representative ATIF-v1.5 upload with intake evaluation_context shaped from a local bundle.",
        "extra": {
            "task_id": "sample-dataset/sample-test-case-a",
            "task_name": "sample-dataset/sample-test-case-a",
            "trial_name": "sample-test-case-a__trial-a",
            "trial_uri": "artifact://sample-run/sample-test-case-a__trial-a",
            "verifier": {
                "started_at": _atif_timestamp(verifier_started_at),
                "finished_at": _atif_timestamp(verifier_finished_at),
            },
            "verifier_result": {"rewards": {"reward": 0.0}},
        },
        "agent": {
            "name": "sample-agent",
            "version": "1.0.0",
            "model_name": "provider/sample-model",
            "extra": {"cwds": ["/app"], "git_branches": ["HEAD"]},
        },
        "final_metrics": {
            "total_prompt_tokens": 51701,
            "total_completion_tokens": 255,
            "total_cached_tokens": 0,
            "total_cost_usd": 0.264321,
            "total_steps": 3,
            "extra": {
                "service_tiers": ["standard"],
                "total_cache_creation_input_tokens": 0,
                "total_cache_read_input_tokens": 0,
            },
        },
        "steps": [
            {
                "step_id": 1,
                "timestamp": _atif_timestamp(user_step_time),
                "source": "user",
                "message": 'You need to create a file called "/app/solution.txt" with the word found in '
                '"secret_file.txt" in the "secrets.7z" archive.',
                "extra": {"is_sidechain": False},
            },
            {
                "step_id": 2,
                "timestamp": _atif_timestamp(agent_step_2_time),
                "source": "agent",
                "model_name": "provider/sample-model",
                "reasoning_content": "The archive exists; inspect available tooling.",
                "message": "Executed Bash tooluse_tuIapjh62ZTI1pildiC9sg",
                "tool_calls": [tool_call],
                "observation": {"results": [tool_observation]},
                "metrics": {
                    "prompt_tokens": 25773,
                    "completion_tokens": 131,
                    "cached_tokens": 0,
                    "cost_usd": 0.13123,
                    "extra": {
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
                        "service_tier": "standard",
                        "cache_creation": {
                            "ephemeral_1h_input_tokens": 0,
                            "ephemeral_5m_input_tokens": 0,
                        },
                    },
                },
                "extra": {
                    "stop_reason": "tool_use",
                    "cwd": "/app",
                    "is_sidechain": False,
                    "tool_use_name": "Bash",
                    "tool_result_metadata": {
                        "is_error": True,
                        "raw_tool_result": {
                            "type": "tool_result",
                            "content": "Exit code 1\n/app/secrets.7z",
                            "is_error": True,
                            "tool_use_id": "tooluse_tuIapjh62ZTI1pildiC9sg",
                        },
                    },
                    "tool_result_is_error": True,
                },
            },
            {
                "step_id": 3,
                "timestamp": _atif_timestamp(agent_step_3_time),
                "source": "agent",
                "model_name": "provider/sample-model",
                "message": "The archive exists but 7z isn't installed. Let me install it and extract the file.",
                "metrics": {
                    "prompt_tokens": 25928,
                    "completion_tokens": 124,
                    "cached_tokens": 0,
                    "cost_usd": 0.133091,
                    "extra": {
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
                        "service_tier": "standard",
                    },
                },
                "observation": {"results": [subagent_observation]},
                "extra": {"stop_reason": "tool_use", "cwd": "/app", "is_sidechain": False},
            },
        ],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 201, ingest_response.text
    assert ingest_response.content == b""

    spans_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[session_id]": body["session_id"],
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 10,
            "sort": "started_at",
        },
    )
    assert spans_response.status_code == 200, spans_response.text
    spans = spans_response.json()["data"]
    assert len(spans) == 7
    spans_by_name = {span["name"]: span for span in spans}
    assert set(spans_by_name) == {
        "sample-agent",
        "user-1",
        "agent-2",
        "Bash",
        "agent-3",
        "subagent-subagents/subagent-session-1.json",
        "harbor.verifier",
    }
    assert {span["session_id"] for span in spans} == {"d074dfb7-3691-443c-b137-720d75e40afa"}

    trajectory = spans_by_name["sample-agent"]
    assert trajectory["kind"] == "AGENT"
    assert trajectory["source"] == "atif"
    assert trajectory["status"] == "error"
    assert trajectory["input"] == body["steps"][0]["message"]
    assert trajectory["output"] == body["steps"][2]["message"]
    assert trajectory["model"] == "provider/sample-model"
    assert trajectory["agent_name"] == "sample-agent"
    # Token and cost accounting lives on the agent step spans that incurred the
    # LLM calls, not on the trajectory coordinator. The trace-level rollup sums
    # per-step metrics; see _trajectory_to_span.
    assert "input_tokens" not in trajectory
    assert "output_tokens" not in trajectory
    assert "cached_tokens" not in trajectory
    assert "total_tokens" not in trajectory
    assert "cost_total_usd" not in trajectory
    assert trajectory["evaluation_context"] == {
        "evaluation_id": evaluation_context["evaluation_id"],
        "evaluation_sha": evaluation_context["evaluation_sha"],
        "evaluation_run_id": evaluation_context["evaluation_run_id"],
        "dataset_id": evaluation_context["dataset_id"],
        "dataset_name": evaluation_context["dataset_name"],
        "dataset_version": evaluation_context["dataset_version"],
        "test_case_id": evaluation_context["test_case_id"],
        "metadata": evaluation_context["metadata"],
    }
    assert "attributes_string" not in trajectory
    trajectory_raw = json.loads(trajectory["raw_attributes"])
    assert trajectory_raw["session_id"] == body["session_id"]
    assert "evaluation_context" not in trajectory_raw
    assert "experiment.metadata" not in trajectory_raw
    assert "evaluation.metadata" not in trajectory_raw
    assert trajectory["started_at"] == _span_started_at(user_step_time)
    assert trajectory["ended_at"] == _span_ended_at(verifier_finished_at)

    for span in spans:
        if span["name"] == "sample-agent":
            continue
        assert "evaluation_context" not in span

    evaluation_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[evaluation_id]": evaluation_context["evaluation_id"],
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 10,
        },
    )
    assert evaluation_response.status_code == 200, evaluation_response.text
    evaluation_spans = evaluation_response.json()["data"]
    assert len(evaluation_spans) == 1
    assert evaluation_spans[0]["name"] == "sample-agent"

    for field, value in {
        "evaluation_id": evaluation_context["evaluation_id"],
        "test_case_id": evaluation_context["test_case_id"],
    }.items():
        filtered = client.get(
            "/apis/intake/v2/workspaces/default/spans",
            params={
                f"filter[{field}]": value,
                "filter[started_at][gte]": _HISTORICAL_GTE,
                "page_size": 10,
            },
        )
        assert filtered.status_code == 200, filtered.text
        filtered_spans = filtered.json()["data"]
        assert len(filtered_spans) == 1
        assert filtered_spans[0]["name"] == "sample-agent"
        assert filtered_spans[0]["evaluation_context"][field] == value

    evaluator_span = spans_by_name["harbor.verifier"]
    assert evaluator_span["kind"] == "EVALUATOR"
    assert evaluator_span["parent_span_id"] == trajectory["span_id"]
    assert evaluator_span["trace_id"] == "d074dfb7-3691-443c-b137-720d75e40afa"
    assert evaluator_span["status"] == "success"
    evaluator_input = json.loads(evaluator_span["input"])
    assert evaluator_input["session_id"] == body["session_id"]
    assert evaluator_input["evaluated_span_id"] == trajectory["span_id"]
    assert evaluator_input["task_id"] == body["extra"]["task_id"]
    assert evaluator_input["task_name"] == body["extra"]["task_name"]
    assert evaluator_input["trial_name"] == body["extra"]["trial_name"]
    assert evaluator_input["trial_uri"] == body["extra"]["trial_uri"]
    evaluator_output = json.loads(evaluator_span["output"])
    assert evaluator_output == {
        "score": 0.0,
        "verifier_result": body["extra"]["verifier_result"],
    }

    user_step = spans_by_name["user-1"]
    assert user_step["kind"] == "AGENT"
    assert user_step["parent_span_id"] == trajectory["span_id"]
    assert user_step["input"] == body["steps"][0]["message"]

    llm_step = spans_by_name["agent-2"]
    assert llm_step["kind"] == "LLM"
    assert llm_step["parent_span_id"] == trajectory["span_id"]
    assert llm_step["status"] == "success"
    assert "error_message" not in llm_step
    assert llm_step["input_tokens"] == 25773
    assert llm_step["output_tokens"] == 131
    assert llm_step["cached_tokens"] == 0
    assert llm_step["total_tokens"] == 25904
    assert Decimal(str(llm_step["cost_total_usd"])) == Decimal("0.13123")
    llm_output = json.loads(llm_step["output"])
    assert llm_output["message"] == body["steps"][1]["message"]
    assert llm_output["reasoning_content"] == body["steps"][1]["reasoning_content"]
    assert llm_output["tool_calls"] == body["steps"][1]["tool_calls"]

    tool_step = spans_by_name["Bash"]
    assert tool_step["kind"] == "TOOL"
    assert tool_step["parent_span_id"] == llm_step["span_id"]
    assert tool_step["tool_name"] == "Bash"
    assert tool_step["status"] == "error"
    assert tool_step["error_message"] == "Exit code 1\n/app/secrets.7z\n\n[error] tool reported failure"
    assert "input_tokens" not in tool_step
    tool_input = json.loads(tool_step["input"])
    assert tool_input == tool_call
    assert json.loads(tool_step["output"]) == tool_observation

    subagent_step = spans_by_name["subagent-subagents/subagent-session-1.json"]
    assert subagent_step["kind"] == "AGENT"
    assert subagent_step["parent_span_id"] == spans_by_name["agent-3"]["span_id"]
    assert subagent_step["trace_id"] == body["session_id"]
    assert json.loads(subagent_step["input"]) == subagent_ref
    assert json.loads(subagent_step["output"]) == subagent_observation

    agent_step_response = client.get(f"/apis/intake/v2/workspaces/default/spans/{spans_by_name['agent-3']['span_id']}")
    assert agent_step_response.status_code == 200, agent_step_response.text
    agent_step = agent_step_response.json()
    assert agent_step["kind"] == "LLM"
    assert "input" not in agent_step
    assert json.loads(agent_step["output"]) == {"message": body["steps"][2]["message"]}
    assert agent_step["input_tokens"] == 25928
    assert agent_step["output_tokens"] == 124
    assert agent_step["total_tokens"] == 26052
    assert Decimal(str(agent_step["cost_total_usd"])) == Decimal("0.133091")

    another_body = {
        "schema_version": "ATIF-v1.7",
        "session_id": "441e9149-e4e6-41c0-82b0-a36802f83d3a",
        "evaluation_context": {
            **evaluation_context,
            "test_case_id": "sample-test-case-b",
            "metadata": {"trial": "sample-test-case-b__trial-b"},
        },
        "extra": {
            "task_name": "sample-dataset/sample-test-case-b",
            "trial_name": "sample-test-case-b__trial-b",
        },
        "agent": body["agent"],
        "steps": [
            {
                "step_id": 1,
                "timestamp": _atif_timestamp(another_session_step_time),
                "source": "user",
                "message": "Run the second sample task.",
            }
        ],
    }
    another_ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=another_body)
    assert another_ingest_response.status_code == 201, another_ingest_response.text
    assert another_ingest_response.content == b""

    evaluation_roots_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[evaluation_id]": evaluation_context["evaluation_id"],
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 20,
            "sort": "started_at",
        },
    )
    assert evaluation_roots_response.status_code == 200, evaluation_roots_response.text
    evaluation_roots = evaluation_roots_response.json()["data"]
    assert len(evaluation_roots) == 2
    assert {span["name"] for span in evaluation_roots} == {"sample-agent"}
    assert {span["evaluation_context"]["evaluation_id"] for span in evaluation_roots} == {
        evaluation_context["evaluation_id"]
    }
    assert {span["session_id"] for span in evaluation_roots} == {
        "d074dfb7-3691-443c-b137-720d75e40afa",
        "441e9149-e4e6-41c0-82b0-a36802f83d3a",
    }

    other_evaluation_run_id = f"{evaluation_run_id}-other"
    same_session_body = {
        "schema_version": "ATIF-v1.7",
        "session_id": body["session_id"],
        "evaluation_context": {**evaluation_context, "evaluation_run_id": other_evaluation_run_id},
        "agent": body["agent"],
        "steps": [body["steps"][0]],
    }
    same_session_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=same_session_body)
    assert same_session_response.status_code == 201, same_session_response.text
    assert same_session_response.content == b""

    other_evaluation_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[evaluation_run_id]": other_evaluation_run_id,
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 10,
        },
    )
    assert other_evaluation_response.status_code == 200, other_evaluation_response.text
    other_evaluation_spans = other_evaluation_response.json()["data"]
    assert len(other_evaluation_spans) == 1
    assert other_evaluation_spans[0]["name"] == "sample-agent"
    assert other_evaluation_spans[0]["evaluation_context"]["evaluation_run_id"] == other_evaluation_run_id

    same_session_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[session_id]": body["session_id"],
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 10,
        },
    )
    assert same_session_response.status_code == 200, same_session_response.text
    same_session_spans_by_name = {span["name"]: span for span in same_session_response.json()["data"]}
    assert same_session_spans_by_name["user-1"]["span_id"] == user_step["span_id"]


def test_atif_trace_tokens_do_not_double_count_when_trajectory_and_steps_both_carry_metrics(
    client: TestClient,
):
    """Regression: emitters like opencode populate both trajectory.final_metrics AND
    per-step metrics that sum to it. The trajectory span must NOT carry token attributes,
    or the trace-level rollup would sum them and report 2x the real total.
    """
    base_time = _recent_base_time()
    user_step_time = base_time
    agent_step_2_time = base_time + timedelta(seconds=5)
    agent_step_3_time = base_time + timedelta(seconds=10)
    body = {
        "schema_version": "ATIF-v1.6",
        "session_id": "atif-rollup-no-double-count",
        "agent": {
            "name": "opencode",
            "version": "1.14.33",
            "model_name": "test-provider/test-model",
        },
        "final_metrics": {
            # If the trajectory span were to keep these as attributes, the rollup
            # would double-count against the per-step metrics below.
            "total_prompt_tokens": 30000,
            "total_completion_tokens": 600,
            "total_cached_tokens": 0,
            "total_cost_usd": 0.45,
            "total_steps": 2,
        },
        "steps": [
            {
                "step_id": 1,
                "timestamp": _atif_timestamp(user_step_time),
                "source": "user",
                "message": "Help me with a task.",
            },
            {
                "step_id": 2,
                "timestamp": _atif_timestamp(agent_step_2_time),
                "source": "agent",
                "model_name": "test-provider/test-model",
                "message": "Here is the first response.",
                "metrics": {
                    "prompt_tokens": 12000,
                    "completion_tokens": 250,
                    "cached_tokens": 0,
                    "cost_usd": 0.18,
                },
            },
            {
                "step_id": 3,
                "timestamp": _atif_timestamp(agent_step_3_time),
                "source": "agent",
                "model_name": "test-provider/test-model",
                "message": "Here is the follow-up.",
                "metrics": {
                    "prompt_tokens": 18000,
                    "completion_tokens": 350,
                    "cached_tokens": 0,
                    "cost_usd": 0.27,
                },
            },
        ],
    }

    ingest_response = client.post("/apis/intake/v2/workspaces/default/ingest/atif", json=body)
    assert ingest_response.status_code == 201, ingest_response.text

    # Trajectory span (kind=AGENT) carries no token or cost attributes.
    spans_response = client.get(
        "/apis/intake/v2/workspaces/default/spans",
        params={
            "filter[session_id]": body["session_id"],
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 20,
            "sort": "started_at",
        },
    )
    assert spans_response.status_code == 200, spans_response.text
    spans = spans_response.json()["data"]
    trajectory = next(span for span in spans if span["kind"] == "AGENT")
    for field in (
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "total_tokens",
        "cost_usd",
        "cost_input_usd",
        "cost_output_usd",
        "cost_total_usd",
    ):
        assert field not in trajectory, f"trajectory span unexpectedly carries {field}: {trajectory.get(field)}"

    # Per-step LLM spans carry their own metrics.
    llm_steps = sorted(
        (span for span in spans if span["kind"] == "LLM"),
        key=lambda span: span["started_at"],
    )
    assert len(llm_steps) == 2
    assert llm_steps[0]["input_tokens"] == 12000
    assert llm_steps[0]["output_tokens"] == 250
    assert llm_steps[1]["input_tokens"] == 18000
    assert llm_steps[1]["output_tokens"] == 350

    # Trace-level rollup equals the sum of per-step metrics, NOT 2x.
    traces_response = client.get(
        "/apis/intake/v2/workspaces/default/traces",
        params={
            "filter[session_id]": body["session_id"],
            "filter[started_at][gte]": _HISTORICAL_GTE,
            "page_size": 10,
        },
    )
    assert traces_response.status_code == 200, traces_response.text
    traces = traces_response.json()["data"]
    assert len(traces) == 1
    trace = traces[0]
    assert trace["input_tokens"] == 30000, (
        f"expected per-step sum (30000); got {trace['input_tokens']} — double-counted?"
    )
    assert trace["output_tokens"] == 600
    assert trace["total_tokens"] == 30600
    assert trace["cost_usd"] == pytest.approx(0.45)


def _create_experiment(client: TestClient, name: str) -> str:
    group_id = _ensure_group(client)
    response = client.post(
        "/apis/intake/v2/workspaces/default/experiments",
        json={
            "name": name,
            "experiment_group_id": group_id,
            "agent_name": "sample-agent",
            "agent_version": "1.0.0",
            "dataset_name": "sample-dataset",
            "dataset_version": "v1",
        },
    )
    assert response.status_code in {201, 409}, response.text
    if response.status_code == 201:
        return response.json()["name"]

    existing = client.get(f"/apis/intake/v2/workspaces/default/experiments/{name}")
    assert existing.status_code == 200, existing.text
    return existing.json()["name"]


def _ensure_group(client: TestClient, name: str = "atif-test-group") -> str:
    response = client.post(
        "/apis/intake/v2/workspaces/default/experiment-groups",
        json={"name": name},
    )
    if response.status_code == 409:
        response = client.get(f"/apis/intake/v2/workspaces/default/experiment-groups/{name}")
    response.raise_for_status()
    return response.json()["id"]
