# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the OpenAI chat-completions ingest endpoint."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

INGEST_URL = "/apis/intake/v2/workspaces/default/ingest/chat-completions"
SPANS_URL = "/apis/intake/v2/workspaces/default/spans"
TRACES_URL = "/apis/intake/v2/workspaces/default/traces"
EVALUATION_CONTEXT: dict[str, Any] = {
    "evaluation_id": "chat-eval",
    "evaluation_sha": "chat-eval-sha",
    "evaluation_run_id": "evalrun-chat-001",
    "test_case_id": "chat-case-001",
    "metadata": {"source": "chat-completions-test"},
}
EXPERIMENT_CONTEXT: dict[str, Any] = {
    "experiment_id": EVALUATION_CONTEXT["evaluation_id"],
    "test_case_id": EVALUATION_CONTEXT["test_case_id"],
}
EXPECTED_CONTEXT_FROM_EXPERIMENT_CONTEXT: dict[str, Any] = {
    "evaluation_id": EVALUATION_CONTEXT["evaluation_id"],
    "test_case_id": EVALUATION_CONTEXT["test_case_id"],
    "metadata": {},
}


def _openai_request(**overrides: Any) -> dict[str, Any]:
    request = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a terse calculator."},
            {"role": "user", "content": "What is 6 times 7?"},
        ],
        "temperature": 0.2,
        "max_tokens": 32,
    }
    request.update(overrides)
    return request


def _openai_response(**overrides: Any) -> dict[str, Any]:
    response = {
        "id": "chatcmpl-test-abc123",
        "object": "chat.completion",
        "created": 1778698885,
        "model": "gpt-4o-mini-2024-08-06",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "42"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 24,
            "completion_tokens": 2,
            "total_tokens": 26,
            "prompt_tokens_details": {"cached_tokens": 16, "audio_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0, "audio_tokens": 0},
        },
        "system_fingerprint": "fp_abc",
    }
    response.update(overrides)
    return response


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_chat_completions_ingest_happy_path(client: TestClient):
    experiment_id = _create_experiment(client, EXPERIMENT_CONTEXT["experiment_id"])
    body = {
        "request": _openai_request(),
        "response": _openai_response(),
        "session_id": "session-happy",
        "experiment_context": {**EXPERIMENT_CONTEXT, "experiment_id": experiment_id},
        "provider": "openai",
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["session_id"] == "session-happy"
    assert payload["span_id"] == "chatcmpl-test-abc123"

    listed = client.get(
        SPANS_URL,
        params={"filter[session_id]": "session-happy", "page_size": 10},
    )
    assert listed.status_code == 200, listed.text
    spans = listed.json()["data"]
    assert len(spans) == 1
    span = spans[0]
    assert span["kind"] == "LLM"
    assert span["source"] == "chat_completions"
    assert span["status"] == "success"
    assert span["name"] == "gpt-4o-mini-2024-08-06"
    assert span["model"] == "gpt-4o-mini-2024-08-06"
    assert span["provider"] == "openai"
    assert span["evaluation_context"] == EXPECTED_CONTEXT_FROM_EXPERIMENT_CONTEXT
    assert "evaluation_run_id" not in span
    assert "raw_attributes" not in span
    assert span["input_tokens"] == 24
    assert span["output_tokens"] == 2
    assert span["total_tokens"] == 26
    assert span["cached_tokens"] == 16
    # input/output preserve the producer payload verbatim
    assert json.loads(span["input"])["messages"][0]["content"] == "You are a terse calculator."
    assert json.loads(span["output"])["choices"][0]["message"]["content"] == "42"

    filtered = client.get(
        SPANS_URL,
        params={"filter[evaluation_id]": EVALUATION_CONTEXT["evaluation_id"], "page_size": 10},
    )
    assert filtered.status_code == 200, filtered.text
    filtered_spans = filtered.json()["data"]
    assert len(filtered_spans) == 1
    assert filtered_spans[0]["span_id"] == "chatcmpl-test-abc123"


def test_chat_completions_ingest_rejects_unknown_experiment_context(client: TestClient):
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-missing-exp"),
        "session_id": "session-missing-exp",
        "experiment_context": {"experiment_id": "missing-exp", "test_case_id": "case-1"},
    }
    response = client.post(INGEST_URL, json=body)

    assert response.status_code == 400, response.text
    assert "must be created before it can be logged" in response.json()["detail"]


def test_chat_completions_ingest_persists_cost_fields(client: TestClient):
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-costs"),
        "session_id": "session-costs",
        "cost_usd": 0.0061,
        "cost_input_usd": 0.0024,
        "cost_output_usd": 0.0037,
        "cost_details": {
            "total": 0.99,
            "input": 0.98,
            "output": 0.97,
            "base_input": 0.0018,
            "cached_input": 0.0004,
            "cache_write": 0.0002,
        },
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-costs"})
    assert listed.status_code == 200, listed.text
    span = listed.json()["data"][0]
    assert Decimal(str(span["cost_total_usd"])) == Decimal("0.0061")
    assert Decimal(str(span["cost_input_usd"])) == Decimal("0.0024")
    assert Decimal(str(span["cost_output_usd"])) == Decimal("0.0037")
    assert Decimal(str(span["cost_details"]["base_input"])) == Decimal("0.0018")
    assert Decimal(str(span["cost_details"]["cached_input"])) == Decimal("0.0004")
    assert Decimal(str(span["cost_details"]["cache_write"])) == Decimal("0.0002")


def test_chat_completions_ingest_rejects_producer_cost_total_alias(client: TestClient):
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-cost-total-alias"),
        "session_id": "session-cost-total-alias",
        "cost_total_usd": 0.0061,
    }
    response = client.post(INGEST_URL, json=body)

    assert response.status_code == 422, response.text


def test_chat_completions_ingest_uses_only_openai_usage_fields(client: TestClient):
    body = {
        "request": _openai_request(model="aws/anthropic/bedrock-claude-opus-4-7"),
        "response": _openai_response(
            id="chatcmpl-openai-usage-only",
            model="aws/anthropic/bedrock-claude-opus-4-7",
            usage={
                "input_tokens": 30,
                "output_tokens": 7,
                "cache_read_input_tokens": 5,
                "cache_creation_input_tokens": 3,
                "output_tokens_details": {"reasoning_tokens": 2},
            },
        ),
        "session_id": "session-openai-usage-only",
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-openai-usage-only"})
    assert listed.status_code == 200, listed.text
    span = listed.json()["data"][0]
    assert "input_tokens" not in span
    assert "output_tokens" not in span
    assert "total_tokens" not in span
    assert "cached_tokens" not in span
    assert span["usage_details"] == {}


# ---------------------------------------------------------------------------
# missing optional metadata
# ---------------------------------------------------------------------------


def test_chat_completions_ingest_handles_missing_usage(client: TestClient):
    response_body = _openai_response()
    response_body.pop("usage")
    response_body.pop("system_fingerprint")

    body = {
        "request": _openai_request(),
        "response": response_body,
        "session_id": "session-no-usage",
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-no-usage"})
    span = listed.json()["data"][0]
    assert span["status"] == "success"
    assert "input_tokens" not in span
    assert "output_tokens" not in span
    assert "cost_total_usd" not in span
    # model still extracted from response.model
    assert span["model"] == "gpt-4o-mini-2024-08-06"


def test_chat_completions_ingest_accepts_deprecated_evaluation_context(client: TestClient):
    _create_experiment(client, EVALUATION_CONTEXT["evaluation_id"])
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-run-id-only"),
        "session_id": "session-run-id-only",
        "evaluation_context": EVALUATION_CONTEXT,
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-run-id-only"})
    assert listed.status_code == 200, listed.text
    span = listed.json()["data"][0]
    assert span["evaluation_context"] == {
        "evaluation_id": EVALUATION_CONTEXT["evaluation_id"],
        "evaluation_sha": EVALUATION_CONTEXT["evaluation_sha"],
        "evaluation_run_id": EVALUATION_CONTEXT["evaluation_run_id"],
        "test_case_id": EVALUATION_CONTEXT["test_case_id"],
        "metadata": EVALUATION_CONTEXT["metadata"],
    }


def test_chat_completions_ingest_rejects_unknown_deprecated_evaluation_context(client: TestClient):
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-missing-deprecated-exp"),
        "session_id": "session-missing-deprecated-exp",
        "evaluation_context": {
            "evaluation_id": "missing-exp",
            "evaluation_run_id": "missing-run",
            "test_case_id": "case-1",
        },
    }
    response = client.post(INGEST_URL, json=body)

    assert response.status_code == 400, response.text


def test_chat_completions_ingest_accepts_partial_deprecated_evaluation_context(client: TestClient):
    _create_experiment(client, "chat-eval")
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-partial-deprecated-context"),
        "session_id": "session-partial-deprecated-context",
        "evaluation_context": {"evaluation_id": "chat-eval", "test_case_id": "case-1"},
    }
    response = client.post(INGEST_URL, json=body)

    assert response.status_code == 201, response.text


def test_chat_completions_ingest_falls_back_when_response_id_missing(client: TestClient):
    response_body = _openai_response()
    response_body.pop("id")

    body = {
        "request": _openai_request(),
        "response": response_body,
        "session_id": "session-no-id",
    }
    first = client.post(INGEST_URL, json=body)
    assert first.status_code == 201, first.text
    first_span_id = first.json()["span_id"]
    assert first_span_id.startswith("chatcmpl-hash-")

    # Same payload → same fallback id → dedupes
    second = client.post(INGEST_URL, json=body)
    assert second.status_code == 201, second.text
    assert second.json()["span_id"] == first_span_id


# ---------------------------------------------------------------------------
# retry / dedupe
# ---------------------------------------------------------------------------


def test_chat_completions_ingest_dedupes_on_retry(client: TestClient):
    body = {
        "request": _openai_request(),
        "response": _openai_response(),
        "session_id": "session-retry",
    }
    first = client.post(INGEST_URL, json=body)
    assert first.status_code == 201, first.text
    second = client.post(INGEST_URL, json=body)
    assert second.status_code == 201, second.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-retry"})
    rows = listed.json()["data"]
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# explicit session grouping
# ---------------------------------------------------------------------------


def test_chat_completions_ingest_groups_by_session_id(client: TestClient):
    for index, prompt in enumerate(["hi", "hello"]):
        body = {
            "request": _openai_request(messages=[{"role": "user", "content": prompt}]),
            "response": _openai_response(id=f"chatcmpl-turn-{index}"),
            "session_id": "shared-session",
        }
        result = client.post(INGEST_URL, json=body)
        assert result.status_code == 201, result.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "shared-session"})
    spans = listed.json()["data"]
    assert len(spans) == 2
    assert {s["span_id"] for s in spans} == {"chatcmpl-turn-0", "chatcmpl-turn-1"}
    assert all(s["session_id"] == "shared-session" for s in spans)

    traces_response = client.get(
        TRACES_URL,
        params={"filter[session_id]": "shared-session", "mode": "summary", "page_size": 10},
    )
    assert traces_response.status_code == 200, traces_response.text
    traces = traces_response.json()["data"]
    assert len(traces) == 2
    assert {trace["id"] for trace in traces} == {"chatcmpl-turn-0", "chatcmpl-turn-1"}
    assert {trace["session_id"] for trace in traces} == {"shared-session"}
    assert all("total_tokens" not in trace for trace in traces)


# ---------------------------------------------------------------------------
# error response
# ---------------------------------------------------------------------------


def test_chat_completions_ingest_marks_error_when_response_contains_error(client: TestClient):
    # Real OpenAI 4xx errors send just the error envelope — no id, no model, no choices.
    body = {
        "request": _openai_request(model="gpt-99"),
        "response": {
            "error": {
                "message": "The model `gpt-99` does not exist or you do not have access to it.",
                "type": "invalid_request_error",
                "code": "model_not_found",
                "param": "model",
            },
        },
        "session_id": "session-error",
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-error"})
    span = listed.json()["data"][0]
    assert span["status"] == "error"
    assert span["error_type"] == "invalid_request_error"
    assert span["error_message"].startswith("The model `gpt-99` does not exist")
    # No response.model → falls back to request.model
    assert span["model"] == "gpt-99"


def test_chat_completions_ingest_rejects_response_with_neither_choices_nor_error(client: TestClient):
    response_body = _openai_response()
    response_body.pop("choices")
    body = {
        "request": _openai_request(),
        "response": response_body,
        "session_id": "session-empty",
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 422, response.text


def test_chat_completions_ingest_rejects_legacy_context_fields(client: TestClient):
    for field in ("project", "experiment_id"):
        body = {
            "request": _openai_request(),
            "response": _openai_response(id=f"chatcmpl-reject-{field}"),
            "session_id": f"session-reject-{field}",
            field: "legacy-value",
        }
        response = client.post(INGEST_URL, json=body)
        assert response.status_code == 422, response.text


def test_chat_completions_ingest_accepts_both_context_shapes_with_experiment_context_precedence(client: TestClient):
    _create_experiment(client, "chat-eval")
    body = {
        "request": _openai_request(),
        "response": _openai_response(id="chatcmpl-both-contexts"),
        "session_id": "session-both-contexts",
        "experiment_context": {"experiment_id": "chat-eval", "test_case_id": "case-1"},
        "evaluation_context": {"evaluation_id": "legacy-eval", "test_case_id": "legacy-case"},
    }
    response = client.post(INGEST_URL, json=body)
    assert response.status_code == 201, response.text

    listed = client.get(SPANS_URL, params={"filter[session_id]": "session-both-contexts"})
    assert listed.status_code == 200, listed.text
    span = listed.json()["data"][0]
    assert span["evaluation_context"]["evaluation_id"] == "chat-eval"
    assert span["evaluation_context"]["test_case_id"] == "case-1"


def _create_experiment(client: TestClient, name: str) -> str:
    group_id = _ensure_group(client)
    response = client.post(
        "/apis/intake/v2/workspaces/default/experiments",
        json={
            "name": name,
            "experiment_group_id": group_id,
            "dataset_name": "chat-dataset",
            "dataset_version": "v1",
        },
    )
    assert response.status_code in {201, 409}, response.text
    if response.status_code == 201:
        return response.json()["name"]

    existing = client.get(f"/apis/intake/v2/workspaces/default/experiments/{name}")
    assert existing.status_code == 200, existing.text
    return existing.json()["name"]


def _ensure_group(client: TestClient, name: str = "chat-completions-test-group") -> str:
    response = client.post(
        "/apis/intake/v2/workspaces/default/experiment-groups",
        json={"name": name},
    )
    if response.status_code == 409:
        response = client.get(f"/apis/intake/v2/workspaces/default/experiment-groups/{name}")
    response.raise_for_status()
    return response.json()["id"]
