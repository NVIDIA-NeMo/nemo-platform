# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, Mock

import pytest
from nemo_platform.types.entities import EntitiesPage
from nemo_platform.types.shared.pagination_data import PaginationData
from nemo_platform_plugin.entities import EntityClient, EntityStoreError


class ExperimentGroup:
    __entity_type__ = "experiment_group"


def _entities_page(**extra_fields: object) -> EntitiesPage:
    return EntitiesPage.model_construct(
        data=[],
        pagination=PaginationData(page=1, page_size=1, current_page_size=0, total_pages=0, total_results=0),
        **extra_fields,
    )


@pytest.mark.asyncio
async def test_list_uses_shorthand_filter_when_filter_string_is_empty() -> None:
    mock_api = Mock()
    mock_api.list = AsyncMock(return_value=_entities_page())
    client = EntityClient(mock_api)

    await client.list(ExperimentGroup, filter_str="", filter_obj={"insight_id": "insight-a"})

    assert mock_api.list.await_args.kwargs["filter"] == '{"data.insight_id": "insight-a"}'


@pytest.mark.asyncio
async def test_count_by_returns_grouped_counts_for_shorthand_filter() -> None:
    mock_api = Mock()
    mock_api.list = AsyncMock(return_value=_entities_page(group_counts={"insight-a": 2}))
    client = EntityClient(mock_api)

    counts = await client.count_by(
        ExperimentGroup,
        "insight_id",
        filter_obj={"insight_id": {"$in": ["insight-a"]}},
    )

    assert counts == {"insight-a": 2}
    mock_api.list.assert_awaited_once_with(
        "experiment_group",
        workspace="default",
        filter='{"data.insight_id": {"$in": ["insight-a"]}}',
        page=1,
        page_size=1,
        extra_query={"count_by": "data.insight_id"},
    )


@pytest.mark.asyncio
async def test_count_by_rejects_response_without_grouped_counts() -> None:
    mock_api = Mock()
    mock_api.list = AsyncMock(return_value=_entities_page())
    client = EntityClient(mock_api)

    with pytest.raises(EntityStoreError, match="Grouped counts not found"):
        await client.count_by(ExperimentGroup, "insight_id")
