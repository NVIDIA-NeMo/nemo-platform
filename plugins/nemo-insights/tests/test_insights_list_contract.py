# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_insights_plugin.entities import Insight
from nemo_insights_plugin.service import InsightsService
from nemo_platform_plugin.entity_client import NemoPaginationInfo, get_entity_client


def _insight(name: str, entity_id: str) -> Insight:
    insight = Insight(
        name=name,
        workspace="default",
        title=f"Title for {name}",
        agent="test-agent",
        description=f"Description for {name}",
    )
    insight._id = entity_id
    return insight


def _list_response(
    items: Sequence[object],
    *,
    page: int = 1,
    page_size: int = 20,
    total_pages: int = 1,
    total_results: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        data=list(items),
        pagination=NemoPaginationInfo(
            page=page,
            page_size=page_size,
            current_page_size=len(items),
            total_pages=total_pages,
            total_results=len(items) if total_results is None else total_results,
        ),
    )


def _app(entity_client: AsyncMock) -> FastAPI:
    app = FastAPI()
    for spec in InsightsService().get_routers():
        app.include_router(spec.router, prefix=spec.prefix)
    app.dependency_overrides[get_entity_client] = lambda: entity_client
    return app


def test_list_insights_counts_only_live_groups_with_one_paginated_batch_shape() -> None:
    requested = [_insight("second-page-a", "insight-a"), _insight("second-page-b", "insight-b")]
    stored_groups = [
        *(SimpleNamespace(insight_id="insight-a", is_deleted=False) for _ in range(101)),
        SimpleNamespace(insight_id="insight-a", is_deleted=True),
        SimpleNamespace(insight_id="insight-outside-page", is_deleted=False),
    ]
    entity_client = AsyncMock()

    async def list_entities(entity_type: Any, **kwargs: Any) -> SimpleNamespace:
        entity_type_name = entity_type.__entity_type__
        if entity_type_name == Insight.__entity_type__:
            return _list_response(
                requested,
                page=2,
                page_size=2,
                total_pages=3,
                total_results=6,
            )
        if entity_type_name != "experiment_group":
            raise AssertionError(f"Unexpected entity query: {entity_type_name}")

        filter_obj = kwargs["filter_obj"]
        assert filter_obj == {
            "insight_id": {"$in": ["insight-a", "insight-b"]},
            "is_deleted": False,
        }
        eligible = [
            group
            for group in stored_groups
            if group.insight_id in filter_obj["insight_id"]["$in"] and not group.is_deleted
        ]
        page = int(kwargs["page"])
        page_size = int(kwargs["page_size"])
        start = (page - 1) * page_size
        return _list_response(
            eligible[start : start + page_size],
            page=page,
            page_size=page_size,
            total_pages=(len(eligible) + page_size - 1) // page_size,
            total_results=len(eligible),
        )

    entity_client.list.side_effect = list_entities

    response = TestClient(_app(entity_client)).get(
        "/v2/workspaces/default/insights",
        params={"page": 2, "page_size": 2},
    )

    assert response.status_code == 200
    assert [(item["id"], item["experiment_group_count"]) for item in response.json()["data"]] == [
        ("insight-a", 101),
        ("insight-b", 0),
    ]
    group_calls = [
        call for call in entity_client.list.await_args_list if call.args[0].__entity_type__ == "experiment_group"
    ]
    assert [call.kwargs["page"] for call in group_calls] == [1, 2]


def test_list_insights_preserves_page_with_null_counts_when_aggregation_fails() -> None:
    entity_client = AsyncMock()
    entity_client.list.side_effect = [
        _list_response([_insight("one", "insight-one"), _insight("two", "insight-two")]),
        RuntimeError("entity store unavailable"),
    ]

    response = TestClient(_app(entity_client)).get("/v2/workspaces/default/insights")

    assert response.status_code == 200
    assert [item["experiment_group_count"] for item in response.json()["data"]] == [None, None]
