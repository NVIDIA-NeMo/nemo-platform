# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Analyst read tool: ``list_insights``.

The analyst no longer mutates Insights through tools — it reports its whole
change-set at the end via the ``analyst_result`` output tool (see
:mod:`nemo_insights_plugin.analyst.result`). This module keeps only the
read-only ``list_insights`` tool, which the analyst uses to see which Insights
already exist for the agent so it can decide what is new versus an update.

By default it calls the typed ``client.insights.insights`` SDK resource backed
by the Insights plugin's Insight CRUD API; when ``insights_output`` is
configured it reads a local YAML file instead. Backend selection lives in
:mod:`nemo_insights_plugin.analyst.analyst_backend`.
"""

import json

from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.entities import InsightStatus
from pydantic_ai import RunContext


async def list_insights(
    ctx: RunContext[AnalystDeps],
    agent: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """List existing Insights for the agent under test.

    Use to see which Insights already exist before deciding whether a finding
    is a new Insight or new evidence for an existing one.

    Args:
        agent: Filter by agent name. Defaults to the analyst's configured
            agent; pass an empty string to list across agents.
        status: Filter by lifecycle status.
        page: Page number (1-indexed).
        page_size: Items per page.
    """
    deps = ctx.deps
    assert deps.backend is not None
    target_agent = agent if agent is not None else deps.agent
    result = await deps.backend.list_insights(
        workspace=deps.workspace,
        page=page,
        page_size=page_size,
        agent=target_agent or None,
        status=InsightStatus(status) if status is not None else None,
    )
    return json.dumps(result.model_dump(mode="json"), indent=2)
