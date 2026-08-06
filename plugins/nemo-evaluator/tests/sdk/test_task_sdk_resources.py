# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the client.evaluator.tasks SDK resources (mocked HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from nemo_evaluator.api.schemas import MetricRef, Revision, Task, TaskInput
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
        revision=1,
        tags={"latest": 1},
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


# --- Revision-aware resources -------------------------------------------------


def _revision_payload(ordinal: int, digest: str) -> dict[str, Any]:
    return Revision(
        revision=ordinal,
        content_hash=digest,
        tags=["latest"] if ordinal == 2 else [],
        created_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")


def test_sync_replace_puts_task_input_to_item_url() -> None:
    http_client = MagicMock()
    http_client.put.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    result = resource.replace("task-1", task=_task_input())

    assert http_client.put.call_args.args[0] == f"{_BASE}/tasks/task-1"
    assert http_client.put.call_args.kwargs["json"]["intent"] == "Answer."
    assert isinstance(result, Task)


def test_sync_replace_passes_project_through() -> None:
    http_client = MagicMock()
    http_client.put.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    resource.replace("task-1", task=_task_input(), project="proj-a")

    assert http_client.put.call_args.kwargs["params"] == {"project": "proj-a"}


def test_sync_retrieve_without_revision_targets_the_item_url() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    resource.retrieve("task-1")

    assert http_client.get.call_args.args[0] == f"{_BASE}/tasks/task-1"


def test_sync_retrieve_with_revision_targets_the_revision_sub_path() -> None:
    """The revision is a path segment, matching the tags route rather than a query parameter."""
    http_client = MagicMock()
    http_client.get.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))
    digest = "a" * 64

    resource.retrieve("task-1", revision=digest)

    assert http_client.get.call_args.args[0] == f"{_BASE}/tasks/task-1/revisions/{digest}"


def test_sync_retrieve_with_tag_targets_the_same_sub_path() -> None:
    """``tag`` and ``revision`` are two names for one route segment, resolved server-side.

    Splitting them is a call-site readability change only, so a tag must reach exactly the URL a
    digest would — a separate query parameter or route would be a behaviour change nobody asked for.
    """
    http_client = MagicMock()
    http_client.get.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    resource.retrieve("task-1", tag="blessed")

    assert http_client.get.call_args.args[0] == f"{_BASE}/tasks/task-1/revisions/blessed"


def test_sync_retrieve_rejects_both_selectors() -> None:
    """Two selectors is ambiguous intent, not a precedence question — refuse rather than pick one."""
    resource = EvaluatorTasksResource(_platform(MagicMock()))

    with pytest.raises(ValueError, match="not both"):
        resource.retrieve("task-1", revision="a" * 64, tag="blessed")


def test_sync_retrieve_percent_encodes_a_tag() -> None:
    """Tags admit ``/`` (``release/v1``), which would otherwise open a path segment."""
    http_client = MagicMock()
    http_client.get.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    resource.retrieve("task-1", tag="release/v1")

    assert http_client.get.call_args.args[0] == f"{_BASE}/tasks/task-1/revisions/release%2Fv1"


def test_sync_list_revisions_parses_the_page() -> None:
    http_client = MagicMock()
    http_client.get.return_value = _response(
        {
            "data": [_revision_payload(2, "b" * 64), _revision_payload(1, "a" * 64)],
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

    page = resource.list_revisions("task-1")

    assert http_client.get.call_args.args[0] == f"{_BASE}/tasks/task-1/revisions"
    assert [r.revision for r in page.data] == [2, 1]
    assert page.data[0].content_hash == "b" * 64


def test_sync_tag_puts_to_the_tag_url_with_the_revision() -> None:
    http_client = MagicMock()
    http_client.put.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))
    digest = "a" * 64

    resource.tag("task-1", tag="blessed", revision=digest)

    assert http_client.put.call_args.args[0] == f"{_BASE}/tasks/task-1/tags/blessed"
    assert http_client.put.call_args.kwargs["params"] == {"revision": digest}


def test_sync_tag_escapes_the_tag_name() -> None:
    """Tag names reach the URL as a path segment; anything needing escaping must be escaped."""
    http_client = MagicMock()
    http_client.put.return_value = _response(_task_payload("task-1"))
    resource = EvaluatorTasksResource(_platform(http_client))

    resource.tag("task-1", tag="release/v1", revision="a" * 64)

    assert http_client.put.call_args.args[0] == f"{_BASE}/tasks/task-1/tags/release%2Fv1"


async def test_async_replace_puts_task_input() -> None:
    http_client = MagicMock()
    http_client.put = AsyncMock(return_value=_response(_task_payload("task-1")))
    resource = AsyncEvaluatorTasksResource(_platform(http_client))

    result = await resource.replace("task-1", task=_task_input())

    assert http_client.put.call_args.args[0] == f"{_BASE}/tasks/task-1"
    assert isinstance(result, Task)


async def test_async_retrieve_with_revision_targets_the_revision_sub_path() -> None:
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=_response(_task_payload("task-1")))
    resource = AsyncEvaluatorTasksResource(_platform(http_client))
    digest = "a" * 64

    await resource.retrieve("task-1", revision=digest)

    assert http_client.get.call_args.args[0] == f"{_BASE}/tasks/task-1/revisions/{digest}"


async def test_async_tag_puts_to_the_tag_url() -> None:
    http_client = MagicMock()
    http_client.put = AsyncMock(return_value=_response(_task_payload("task-1")))
    resource = AsyncEvaluatorTasksResource(_platform(http_client))

    await resource.tag("task-1", tag="blessed", revision="a" * 64)

    assert http_client.put.call_args.args[0] == f"{_BASE}/tasks/task-1/tags/blessed"
