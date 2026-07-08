# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Intake's plugin-owned typed client."""

from __future__ import annotations

import json
from importlib.metadata import entry_points
from unittest.mock import AsyncMock

import httpx
from nemo_intake_client.client import AsyncIntakeClient
from nemo_intake_client.models import (
    AtifAgent,
    AtifIngestRequest,
    AtifStepAgent,
    EvaluatorResultDataType,
    EvaluatorResultInput,
    ExperimentGroupRequest,
    TraceFilter,
)
from nemo_platform_plugin.sdk import NemoPluginSDKResources

BASE_URL = "http://testserver"
WORKSPACE = "default"


def _response(status_code: int, payload: object | None = None) -> httpx.Response:
    request = httpx.Request("GET", BASE_URL)
    if payload is None:
        return httpx.Response(status_code, content=b"", request=request)
    return httpx.Response(status_code, json=payload, request=request)


def _client() -> tuple[AsyncIntakeClient, AsyncMock]:
    http_client = AsyncMock(spec=httpx.AsyncClient)
    return AsyncIntakeClient(base_url=BASE_URL, workspace=WORKSPACE, http_client=http_client), http_client


def test_sdk_entry_point_loads_intake_resources() -> None:
    entry_point = next(entry_point for entry_point in entry_points(group="nemo.sdk") if entry_point.name == "intake")

    assert isinstance(entry_point.load(), NemoPluginSDKResources)


async def test_create_atif_serializes_shared_request_model() -> None:
    client, http_client = _client()
    http_client.request.return_value = _response(201)
    body = AtifIngestRequest(
        schema_version="ATIF-v1.7",
        session_id="session-1",
        agent=AtifAgent(name="agent", version="1"),
        steps=[AtifStepAgent(source="agent", step_id=1, message="done")],
    )

    await client.create_atif(body=body)

    method, url = http_client.request.call_args.args
    assert method == "POST"
    assert url == f"{BASE_URL}/apis/intake/v2/workspaces/{WORKSPACE}/ingest/atif"
    assert json.loads(http_client.request.call_args.kwargs["content"])["session_id"] == "session-1"


async def test_create_evaluator_result_parses_response() -> None:
    client, http_client = _client()
    http_client.request.return_value = _response(
        201,
        {
            "evaluator_result_id": "eval-1",
            "span_id": "span-1",
            "session_id": "session-1",
            "workspace": WORKSPACE,
            "name": "accuracy.score",
            "value": 1.0,
            "data_type": "NUMERIC",
            "created_at": "2026-01-01T00:00:00Z",
            "ingested_at": "2026-01-01T00:00:00Z",
        },
    )

    response = await client.create_evaluator_result(
        body=EvaluatorResultInput(
            span_id="span-1",
            session_id="session-1",
            name="accuracy.score",
            value=1.0,
            data_type=EvaluatorResultDataType.NUMERIC,
        )
    )

    assert response.data().evaluator_result_id == "eval-1"
    payload = json.loads(http_client.request.call_args.kwargs["content"])
    assert "string_value" not in payload
    assert "comment" not in payload


async def test_create_experiment_group_exist_ok_fetches_existing_group() -> None:
    client, http_client = _client()
    name = "existing-group"
    http_client.request.side_effect = [
        _response(409, {"detail": "already exists"}),
        _response(
            200,
            {
                "id": "group-1",
                "name": name,
                "workspace": WORKSPACE,
                "default_sort": "-created_at",
            },
        ),
    ]

    response = await client.create_experiment_group(
        body=ExperimentGroupRequest(name=name),
        exist_ok=True,
    )

    assert response.data().name == name
    assert http_client.request.call_args_list[1].args[1] == (
        f"{BASE_URL}/apis/intake/v2/workspaces/{WORKSPACE}/experiment-groups/{name}"
    )


async def test_list_traces_serializes_filter_and_parses_page() -> None:
    client, http_client = _client()
    http_client.request.return_value = _response(
        200,
        {
            "data": [
                {
                    "id": "trace-1",
                    "root_span_id": "span-1",
                    "session_id": "session-1",
                    "workspace": WORKSPACE,
                    "started_at": "2026-01-01T00:00:00Z",
                    "status": "success",
                }
            ],
            "pagination": {"page": 1, "page_size": 10, "total_pages": 1, "total_results": 1},
        },
    )

    response = await client.list_traces(query_params={"filter": TraceFilter(session_id="session-1")})
    traces = [trace async for trace in response.items()]

    assert traces[0].root_span_id == "span-1"
    assert http_client.request.call_args.kwargs["params"]["filter"] == '{"session_id": "session-1"}'


async def test_list_span_evaluator_results_parses_root_list() -> None:
    client, http_client = _client()
    http_client.request.return_value = _response(200, [])

    response = await client.list_span_evaluator_results(span_id="span-1")

    assert response.data().root == []
