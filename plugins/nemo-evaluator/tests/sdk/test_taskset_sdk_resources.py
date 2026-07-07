# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the client.evaluator.tasksets SDK resources (mocked HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from nemo_evaluator.api.schemas import TaskRef, Taskset, TasksetInput
from nemo_evaluator.sdk.taskset_resources import AsyncEvaluatorTasksetsResource, EvaluatorTasksetsResource

_BASE = "http://localhost:8080/apis/evaluator/v2/workspaces/default"


def _taskset_payload(name: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return Taskset(
        id=f"taskset-{name}",
        name=name,
        workspace="default",
        description="A grouping.",
        tasks=[TaskRef("default/task-a")],
        created_at=now,
        updated_at=now,
    ).model_dump(mode="json")


def _taskset_input() -> TasksetInput:
    return TasksetInput(description="A grouping.", tasks=[TaskRef("default/task-a")])


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


def test_sync_create_posts_taskset_input_to_item_url() -> None:
    http_client = MagicMock()
    http_client.post.return_value = _response(_taskset_payload("ts-1"))
    resource = EvaluatorTasksetsResource(_platform(http_client))

    result = resource.create("ts-1", taskset=_taskset_input())

    assert isinstance(result, Taskset)
    assert result.name == "ts-1"
    assert http_client.post.call_args[0][0] == f"{_BASE}/tasksets/ts-1"
    assert http_client.post.call_args.kwargs["json"]["tasks"] == ["default/task-a"]


def test_sync_retrieve_targets_item_url_and_parses_dto() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(_taskset_payload("ts-1"))
    resource = EvaluatorTasksetsResource(_platform(http_client))

    result = resource.retrieve("ts-1")

    assert isinstance(result, Taskset)
    assert isinstance(result.tasks[0], TaskRef)
    assert http_client.get.call_args[0][0] == f"{_BASE}/tasksets/ts-1"


def test_sync_list_parses_page() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(
        {
            "data": [_taskset_payload("a"), _taskset_payload("b")],
            "pagination": {
                "page": 1,
                "page_size": 100,
                "current_page_size": 2,
                "total_pages": 1,
                "total_results": 2,
            },
        }
    )
    resource = EvaluatorTasksetsResource(_platform(http_client))

    page = resource.list(sort="-created_at")

    assert {t.name for t in page.data} == {"a", "b"}
    assert http_client.get.call_args[0][0] == f"{_BASE}/tasksets"
    assert http_client.get.call_args.kwargs["params"]["sort"] == "-created_at"


def test_sync_delete_issues_delete_request() -> None:
    http_client = MagicMock()
    http_client.delete.return_value = _response({})
    resource = EvaluatorTasksetsResource(_platform(http_client))

    resource.delete("ts-1")

    assert http_client.delete.call_args[0][0] == f"{_BASE}/tasksets/ts-1"


async def test_async_retrieve_parses_dto() -> None:
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_response(_taskset_payload("ts-9")))
    resource = AsyncEvaluatorTasksetsResource(_platform(http_client))

    result = await resource.retrieve("ts-9")

    assert isinstance(result, Taskset)
    assert result.name == "ts-9"
    assert http_client.get.call_args[0][0] == f"{_BASE}/tasksets/ts-9"
