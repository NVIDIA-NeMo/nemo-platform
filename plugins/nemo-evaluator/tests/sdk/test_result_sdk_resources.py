# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the client.evaluator.{agent_eval_results,eval_results} SDK resources.

Drives the resources against a mocked HTTP client, asserting the URL they target and that the
response JSON is deserialized into the typed API DTO.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from nemo_evaluator.api.schemas import AgentEvalResult, EvaluateResult
from nemo_evaluator.sdk.result_resources import (
    AsyncEvaluatorEvalResultsResource,
    EvaluatorAgentEvalResultsResource,
    EvaluatorEvalResultsResource,
)
from nemo_evaluator_sdk.values.results import AggregatedMetricResult

_BASE = "http://localhost:8080/apis/evaluator/v2/workspaces/default"


def _agent_payload(name: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return AgentEvalResult(
        id=f"agent_eval_result-{name}",
        name=name,
        workspace="default",
        job_id=name,
        target_kind="codex",
        target_name="gpt-5.5",
        target_url=None,
        scores=AggregatedMetricResult(scores=[]),
        bundle_ref="fileset://default/agent-eval-results#b",
        created_at=now,
        updated_at=now,
    ).model_dump(mode="json")


def _eval_payload(name: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return EvaluateResult(
        id=f"evaluate_result-{name}",
        name=name,
        workspace="default",
        job_id=name,
        target_kind="model",
        target_name="m",
        target_url="https://m.test/v1/chat/completions",
        scores=AggregatedMetricResult(scores=[]),
        bundle_ref="fileset://default/eval-results#b",
        created_at=now,
        updated_at=now,
        dataset_ref="default/ds",
        metric_types=["exact_match"],
    ).model_dump(mode="json")


def _page(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": items,
        "pagination": {
            "page": 1,
            "page_size": 100,
            "current_page_size": len(items),
            "total_pages": 1,
            "total_results": len(items),
        },
    }


def _response(payload: dict[str, Any]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _platform(http_client: Any) -> MagicMock:
    platform = MagicMock()
    platform._client = http_client
    platform.base_url = "http://localhost:8080"
    platform.workspace = "default"
    platform.default_headers = {}
    platform.timeout = 30
    return platform


# ---- sync ------------------------------------------------------------------


def test_sync_retrieve_agent_eval_targets_item_url_and_parses_dto() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(_agent_payload("job-1"))
    resource = EvaluatorAgentEvalResultsResource(_platform(http_client))

    result = resource.retrieve("job-1")

    assert isinstance(result, AgentEvalResult)
    assert result.job_id == "job-1"
    assert result.target_kind == "codex"
    assert http_client.get.call_args[0][0] == f"{_BASE}/agent-eval-results/job-1"


def test_sync_list_eval_results_parses_dtos_and_targets_collection() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(_page([_eval_payload("a"), _eval_payload("b")]))
    resource = EvaluatorEvalResultsResource(_platform(http_client))

    page = resource.list(sort="-created_at")

    assert {r.name for r in page.data} == {"a", "b"}
    assert all(isinstance(r, EvaluateResult) for r in page.data)
    assert page.data[0].dataset_ref == "default/ds"
    assert page.pagination is not None and page.pagination.total_results == 2
    assert http_client.get.call_args[0][0] == f"{_BASE}/eval-results"
    assert http_client.get.call_args.kwargs["params"]["sort"] == "-created_at"


def test_sync_list_encodes_trait_filters_as_bracket_params() -> None:
    # The route filters via filter[field]=value bracket params; the SDK must encode them so a
    # caller can narrow by job/target/dataset without hand-building query strings.
    http_client = MagicMock()
    http_client.get.return_value = _response(_page([]))
    resource = EvaluatorEvalResultsResource(_platform(http_client))

    resource.list(job_id="j1", target_kind="model", dataset_ref="ws/ds")

    params = http_client.get.call_args.kwargs["params"]
    assert params["filter[job_id]"] == "j1"
    assert params["filter[target_kind]"] == "model"
    assert params["filter[dataset_ref]"] == "ws/ds"
    # Unset filters are omitted entirely (no empty filter[...] keys).
    assert "filter[target_name]" not in params


def test_sync_list_parses_payload_with_none_fields_omitted() -> None:
    # Regression guard: the list route serializes with response_model_exclude_none, so an offline
    # result (no target / inline dataset) arrives with target_*/dataset_ref *absent*. The DTO must
    # still deserialize (those fields default to None) — a live round-trip caught this; this locks it.
    item = _eval_payload("offline")
    for dropped in ("target_kind", "target_name", "target_url", "dataset_ref"):
        item.pop(dropped, None)
    http_client = MagicMock()
    http_client.get.return_value = _response(_page([item]))
    resource = EvaluatorEvalResultsResource(_platform(http_client))

    (result,) = resource.list().data

    assert result.target_kind is None
    assert result.target_name is None
    assert result.target_url is None
    assert result.dataset_ref is None
    assert result.metric_types == ["exact_match"]


def test_sync_delete_issues_delete_request() -> None:
    http_client = MagicMock()
    http_client.delete.return_value = _response({})
    resource = EvaluatorEvalResultsResource(_platform(http_client))

    resource.delete("job-1")

    assert http_client.delete.call_args[0][0] == f"{_BASE}/eval-results/job-1"


# ---- async -----------------------------------------------------------------


async def test_async_retrieve_eval_result_parses_dto() -> None:
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_response(_eval_payload("job-9")))
    resource = AsyncEvaluatorEvalResultsResource(_platform(http_client))

    result = await resource.retrieve("job-9")

    assert isinstance(result, EvaluateResult)
    assert result.metric_types == ["exact_match"]
    assert http_client.get.call_args[0][0] == f"{_BASE}/eval-results/job-9"
