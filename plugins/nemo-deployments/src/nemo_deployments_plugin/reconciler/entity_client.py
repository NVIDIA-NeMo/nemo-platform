# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entity client helpers for paginated listing and prerequisite resolution."""

from __future__ import annotations

from typing import TypeVar

from nemo_deployments_plugin.entities import Deployment
from nemo_platform_plugin.entity import NemoEntity
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError
from nemo_platform_plugin.filter_ops import ComparisonOperation, FilterOperator

EntityT = TypeVar("EntityT", bound=NemoEntity)

DEFAULT_LIST_PAGE_SIZE = 100


async def list_all_pages(
    entities: NemoEntitiesClient,
    entity_type: type[EntityT],
    *,
    workspace: str = "-",
    page_size: int = DEFAULT_LIST_PAGE_SIZE,
    filter_operation: ComparisonOperation | None = None,
) -> list[EntityT]:
    """Fetch all pages for a cross-workspace entity list query."""
    collected: list[EntityT] = []
    page = 1
    while True:
        result = await entities.list(
            entity_type,
            workspace=workspace,
            page=page,
            page_size=page_size,
            filter_operation=filter_operation,
        )
        collected.extend(result.data)
        pagination = result.pagination
        if pagination is None or page >= pagination.total_pages:
            break
        page += 1
    return collected


async def get_deployment_for_config_name(
    entities: NemoEntitiesClient,
    *,
    workspace: str,
    config_name: str,
) -> Deployment | None:
    """Resolve a Deployment entity for a DeploymentConfig name (any terminal status)."""
    deployments = await list_all_pages(
        entities,
        Deployment,
        workspace=workspace,
        filter_operation=ComparisonOperation(
            operator=FilterOperator.EQ,
            field="deployment_config",
            value=config_name,
        ),
    )
    if deployments:
        return deployments[0]

    try:
        dep = await entities.get(Deployment, name=config_name, workspace=workspace)
    except NemoEntityNotFoundError:
        return None

    if dep.deployment_config == config_name:
        return dep
    return None
