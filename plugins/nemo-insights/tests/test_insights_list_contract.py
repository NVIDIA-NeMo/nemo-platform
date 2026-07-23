# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_insights_plugin.entities import Insight
from nemo_insights_plugin.service import InsightsService
from nemo_platform_plugin.entity_client import NemoPaginationInfo, get_entity_client
from nmp.intake.entities.experiments import ExperimentGroup


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


def _app(entity_client: AsyncMock) -> FastAPI:
    app = FastAPI()
    for spec in InsightsService().get_routers():
        app.include_router(spec.router, prefix=spec.prefix)
    app.dependency_overrides[get_entity_client] = lambda: entity_client
    return app


def test_list_insights_uses_grouped_counts_and_defaults_missing_ids_to_zero() -> None:
    entity_client = AsyncMock()
    insights = [_insight("first", "insight-a"), _insight("second", "insight-b")]
    entity_client.list.return_value = SimpleNamespace(
        data=insights,
        pagination=NemoPaginationInfo(
            page=1,
            page_size=20,
            current_page_size=len(insights),
            total_pages=1,
            total_results=len(insights),
        ),
    )
    entity_client.count_by.return_value = {"insight-a": 3}

    response = TestClient(_app(entity_client)).get("/v2/workspaces/default/insights")

    assert response.status_code == 200
    assert [(item["id"], item["experiment_group_count"]) for item in response.json()["data"]] == [
        ("insight-a", 3),
        ("insight-b", 0),
    ]
    entity_client.count_by.assert_awaited_once_with(
        ExperimentGroup,
        "insight_id",
        workspace="default",
        filter_obj={
            "insight_id": {"$in": ["insight-a", "insight-b"]},
            "is_deleted": False,
        },
    )
