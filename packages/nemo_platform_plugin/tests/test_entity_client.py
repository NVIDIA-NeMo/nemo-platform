# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, Mock

import pytest
from nemo_platform.types.entities import EntitiesPage
from nemo_platform.types.shared.pagination_data import PaginationData
from nemo_platform_plugin.entities import EntityClient, EntityStoreError


class ExperimentGroup:
    __entity_type__ = "experiment_group"


def _entities_page(group_counts: dict[str, int] | None = None) -> EntitiesPage:
    return EntitiesPage.model_construct(
        data=[],
        pagination=PaginationData(page=1, page_size=1, current_page_size=0, total_pages=0, total_results=0),
        group_counts=group_counts,
    )


@pytest.mark.asyncio
async def test_count_by_returns_grouped_counts_for_shorthand_filter() -> None:
    mock_api = Mock()
    mock_api.list = AsyncMock(return_value=_entities_page(group_counts={"insight-a": 2}))
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
    assert mock_api.list.await_args.kwargs["extra_query"] == {"count_by": "data.insight_id"}


@pytest.mark.asyncio
async def test_count_by_rejects_response_without_grouped_counts() -> None:
    mock_api = Mock()
    mock_api.list = AsyncMock(return_value=_entities_page())
    client = EntityClient(mock_api)

    with pytest.raises(EntityStoreError, match="Grouped counts not found"):
        await client.count_by(ExperimentGroup, "insight_id")


@pytest.mark.asyncio
async def test_count_by_rejects_non_direct_field() -> None:
    mock_api = Mock()
    mock_api.list = AsyncMock(return_value=_entities_page())
    client = EntityClient(mock_api)

    with pytest.raises(ValueError, match="direct entity data field"):
        await client.count_by(ExperimentGroup, "data.insight_id")
