# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, Mock

import pytest
from nemo_platform_plugin.entities import EntityClient, EntityStoreError


class ExperimentGroup:
    __entity_type__ = "experiment_group"


def _entities_page(group_counts: dict[str, int] | None = None) -> Mock:
    """Wrap a list response envelope so ``http_response.json()`` returns it.

    ``count_by`` reads ``group_counts`` off the raw envelope rather than the
    parsed item page, so the mock only needs the raw body.
    """
    body: dict[str, object] = {
        "data": [],
        "pagination": {
            "page": 1,
            "page_size": 1,
            "current_page_size": 0,
            "total_pages": 0,
            "total_results": 0,
        },
    }
    if group_counts is not None:
        body["group_counts"] = group_counts

    resp = Mock()
    resp.http_response = Mock()
    resp.http_response.json = Mock(return_value=body)
    return resp


@pytest.mark.asyncio
async def test_count_by_returns_grouped_counts_for_shorthand_filter() -> None:
    mock_api = Mock()
    mock_api.list_entities = AsyncMock(return_value=_entities_page(group_counts={"insight-a": 2}))
    client = EntityClient(mock_api)

    counts = await client.count_by(
        ExperimentGroup,
        "insight_id",
        filter_obj={
            "insight_id": {"$in": ["insight-a"]},
            "is_deleted": False,
        },
    )

    assert counts == {"insight-a": 2}
    query_params = mock_api.list_entities.await_args.kwargs["query_params"]
    assert query_params["filter"] == ('{"data.insight_id": {"$in": ["insight-a"]}, "data.is_deleted": false}')
    assert query_params["count_by"] == "data.insight_id"
    assert query_params["page_size"] == 1


@pytest.mark.asyncio
async def test_count_by_rejects_response_without_grouped_counts() -> None:
    mock_api = Mock()
    mock_api.list_entities = AsyncMock(return_value=_entities_page())
    client = EntityClient(mock_api)

    with pytest.raises(EntityStoreError, match="Grouped counts not found"):
        await client.count_by(ExperimentGroup, "insight_id")

    # No filter supplied, so the request must omit the filter param entirely.
    assert "filter" not in mock_api.list_entities.await_args.kwargs["query_params"]


@pytest.mark.asyncio
async def test_count_by_rejects_non_direct_field() -> None:
    mock_api = Mock()
    client = EntityClient(mock_api)

    with pytest.raises(ValueError, match="direct entity data field"):
        await client.count_by(ExperimentGroup, "data.insight_id")
