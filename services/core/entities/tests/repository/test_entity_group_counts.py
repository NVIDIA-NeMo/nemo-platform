# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for grouped entity counts."""

import pytest
from nmp.common.api.filter import ComparisonOperation, FilterOperator, LogicalOperation
from nmp.core.entities.app.repository import SQLAlchemyEntityRepository

pytestmark = pytest.mark.asyncio


async def test_counts_filtered_entities_grouped_by_json_field(
    entity_repo: SQLAlchemyEntityRepository, setup_workspaces
):
    """Count only live experiment groups for the requested insights."""
    for name, insight_id in (("a-1", "insight-a"), ("a-2", "insight-a"), ("b-1", "insight-b")):
        await entity_repo.create_entity(
            workspace="workspace-1",
            entity_type="experiment_group",
            name=name,
            data={"insight_id": insight_id, "is_deleted": False},
        )

    await entity_repo.create_entity(
        workspace="workspace-1",
        entity_type="experiment_group",
        name="deleted",
        data={"insight_id": "insight-a", "is_deleted": True},
    )
    await entity_repo.create_entity(
        workspace="workspace-1",
        entity_type="experiment_group",
        name="unlinked",
        data={"is_deleted": False},
    )
    await entity_repo.create_entity(
        workspace="workspace-2",
        entity_type="experiment_group",
        name="other-workspace",
        data={"insight_id": "insight-a", "is_deleted": False},
    )
    await entity_repo.create_entity(
        workspace="workspace-1",
        entity_type="other_type",
        name="other-type",
        data={"insight_id": "insight-a", "is_deleted": False},
    )

    filter_op = LogicalOperation(
        operator=FilterOperator.AND,
        operations=[
            ComparisonOperation(field="data.insight_id", operator=FilterOperator.IN, value=["insight-a", "insight-b"]),
            ComparisonOperation(field="data.is_deleted", operator=FilterOperator.EQ, value=False),
        ],
    )

    counts = await entity_repo.count_entities_by(
        workspace="workspace-1",
        entity_type="experiment_group",
        group_by="data.insight_id",
        filter_op=filter_op,
    )

    assert counts == {"insight-a": 2, "insight-b": 1}


async def test_counts_base_field_literal_null(entity_repo: SQLAlchemyEntityRepository, setup_workspaces):
    await entity_repo.create_entity(
        workspace="workspace-1",
        entity_type="experiment_group",
        name="null",
        data={},
    )

    counts = await entity_repo.count_entities_by(
        workspace="workspace-1",
        entity_type="experiment_group",
        group_by="name",
    )

    assert counts == {"null": 1}


async def test_omits_missing_and_null_json_group_keys(entity_repo: SQLAlchemyEntityRepository, setup_workspaces):
    for name, data in (
        ("linked", {"insight_id": "insight-a"}),
        ("missing", {}),
        ("null", {"insight_id": None}),
    ):
        await entity_repo.create_entity(
            workspace="workspace-1",
            entity_type="experiment_group",
            name=name,
            data=data,
        )

    counts = await entity_repo.count_entities_by(
        workspace="workspace-1",
        entity_type="experiment_group",
        group_by="data.insight_id",
    )

    assert counts == {"insight-a": 1}
