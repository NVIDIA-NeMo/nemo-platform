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
    entities = (
        ("workspace-1", "experiment_group", "a-1", {"insight_id": "insight-a", "is_deleted": False}),
        ("workspace-1", "experiment_group", "a-2", {"insight_id": "insight-a", "is_deleted": False}),
        ("workspace-1", "experiment_group", "b-1", {"insight_id": "insight-b", "is_deleted": False}),
        ("workspace-1", "experiment_group", "deleted", {"insight_id": "insight-a", "is_deleted": True}),
        ("workspace-1", "experiment_group", "unlinked", {"is_deleted": False}),
        ("workspace-2", "experiment_group", "other-workspace", {"insight_id": "insight-a", "is_deleted": False}),
        ("workspace-1", "other_type", "other-type", {"insight_id": "insight-a", "is_deleted": False}),
    )
    for workspace, entity_type, name, data in entities:
        await entity_repo.create_entity(
            workspace=workspace,
            entity_type=entity_type,
            name=name,
            data=data,
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
