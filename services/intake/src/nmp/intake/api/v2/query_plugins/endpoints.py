# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Query-plugin endpoints

Static manifest + generic run endpoint for deployed query plugins. Plugin-specific response
shapes live in org/local plugin modules and in Studio plugin packages — not in platform OpenAPI.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from nmp.intake.query_plugins.base import QueryPlugin
from nmp.intake.query_plugins.registry import get_query_plugin, query_plugin_ids
from nmp.intake.query_plugins.runner import QueryPluginRunner
from nmp.intake.spans.api.dependencies import require_workspace_access
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_workspace_access)])

QUERY_PLUGINS_TAG = "Query Plugins"


async def _run_or_503(
    runner: QueryPluginRunner, plugin: QueryPlugin, *, workspace: str, experiment_id: str
) -> BaseModel:
    """Run a plugin, converting backend failures to a deterministic 503.

    ``runner is None`` already covers ClickHouse being unconfigured. This covers the configured-but-
    unreachable case (connection drop, query timeout): mirror the per-session read path and raise a
    503 instead of letting it bubble as an opaque 500 (which also strips CORS headers in the browser).
    """
    try:
        return await runner.run(plugin, workspace=workspace, experiment_ids=[experiment_id])
    except Exception as exc:
        logger.exception("Query plugin %s failed for workspace=%s experiment=%s", plugin.id, workspace, experiment_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telemetry store unavailable.",
        ) from exc


class QueryPluginInfo(BaseModel):
    id: str


class QueryPluginManifest(BaseModel):
    """Deployed query-plugin ids, used by Studio's ``consumesQueryPlugins`` availability check."""

    query_plugins: list[QueryPluginInfo] = Field(default_factory=list)


class QueryPluginResult(BaseModel):
    """Generic wrapper for any registered query plugin's typed output."""

    query_plugin_id: str
    data: dict[str, Any]


def _get_clickhouse_client(request: Request) -> ClickHouseSpanClient | None:
    service = getattr(request.app.state, "intake_service", None) or getattr(request.app.state, "service", None)
    if service is None:
        return None
    return getattr(service, "clickhouse_client", None)


def get_query_plugin_runner(request: Request) -> QueryPluginRunner | None:
    """Best-effort runner; ``None`` when ClickHouse is not configured (same posture as rollups)."""
    client = _get_clickhouse_client(request)
    return QueryPluginRunner(client) if client is not None else None


QueryPluginRunnerDep = Annotated[QueryPluginRunner | None, Depends(get_query_plugin_runner)]


@router.get(
    "/v2/workspaces/{workspace}/query-plugins",
    response_model=QueryPluginManifest,
    tags=[QUERY_PLUGINS_TAG],
)
async def list_query_plugins(workspace: str) -> QueryPluginManifest:
    """List the query-plugin ids deployed in this service (additive; not experiment rollups)."""
    return QueryPluginManifest(query_plugins=[QueryPluginInfo(id=plugin_id) for plugin_id in query_plugin_ids()])


@router.get(
    "/v2/workspaces/{workspace}/query-plugins/{query_plugin_id}",
    response_model=QueryPluginResult,
    tags=[QUERY_PLUGINS_TAG],
    summary="Run a query plugin for one experiment.",
)
async def run_query_plugin(
    workspace: str,
    query_plugin_id: str,
    runner: QueryPluginRunnerDep,
    experiment_id: Annotated[str, Query(description="Experiment name to scope this query plugin to.")],
) -> QueryPluginResult:
    """Execute a deployed query plugin and return its output as generic JSON."""
    if runner is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ClickHouse is not available for query plugins.",
        )
    plugin = get_query_plugin(query_plugin_id)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query plugin not registered.")
    result = await _run_or_503(runner, plugin, workspace=workspace, experiment_id=experiment_id)
    return QueryPluginResult(
        query_plugin_id=query_plugin_id,
        data=result.model_dump(mode="json"),
    )
