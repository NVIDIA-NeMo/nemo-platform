# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the client.evaluator.tasks SDK resources (mocked HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from nemo_evaluator.api.schemas import MetricRef, Task, TaskInput
from nemo_evaluator.sdk.task_resources import AsyncEvaluatorTasksResource, EvaluatorTasksResource

_BASE = "http://localhost:8080/apis/evaluator/v2/workspaces/default"


def _task_payload(name: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return Task(
        id=f"task-{name}",
        name=name,
        workspace="default",
        intent="Answer the question.",
        inputs={"instruction": "What is 2+2?"},
        metrics=[MetricRef("default/stored-metric")],
        created_at=now,
        updated_at=now,
    ).model_dump(mode="json")


def _task_input() -> TaskInput:
    return TaskInput(intent="Answer.", inputs={"instruction": "x"}, metrics=[MetricRef("default/stored-metric")])


def _response(payload: Any) -> MagicMock:
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


def test_sync_create_posts_task_input_to_item_url() -> None:
    http_client = MagicMock()
    http_client.post.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    result = resource.create("task-1", task=_task_input())

    assert isinstance(result, Task)
    assert result.name == "task-1"
    assert http_client.post.call_args[0][0] == f"{_BASE}/tasks/task-1"
    assert http_client.post.call_args.kwargs["json"]["intent"] == "Answer."


def test_sync_retrieve_targets_item_url_and_parses_dto() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    result = resource.retrieve("task-1")

    assert isinstance(result, Task)
    assert isinstance(result.metrics[0], MetricRef)
    assert http_client.get.call_args[0][0] == f"{_BASE}/tasks/task-1"


def test_sync_list_parses_page() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(
        {
            "data": [_task_payload("a"), _task_payload("b")],
            "pagination": {
                "page": 1,
                "page_size": 100,
                "current_page_size": 2,
                "total_pages": 1,
                "total_results": 2,
            },
        }
    )
    resource = EvaluatorTasksResource(_platform(http_client))

    page = resource.list(sort="-created_at")

    assert {t.name for t in page.data} == {"a", "b"}
    assert http_client.get.call_args[0][0] == f"{_BASE}/tasks"
    assert http_client.get.call_args.kwargs["params"]["sort"] == "-created_at"


def test_sync_delete_issues_delete_request() -> None:
    http_client = MagicMock()
    http_client.delete.return_value = _response({})
    resource = EvaluatorTasksResource(_platform(http_client))

    resource.delete("task-1")

    assert http_client.delete.call_args[0][0] == f"{_BASE}/tasks/task-1"


async def test_async_retrieve_parses_dto() -> None:
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_response(_task_payload("task-9")))
    resource = AsyncEvaluatorTasksResource(_platform(http_client))

    result = await resource.retrieve("task-9")

    assert isinstance(result, Task)
    assert result.name == "task-9"
    assert http_client.get.call_args[0][0] == f"{_BASE}/tasks/task-9"
