# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Insights plugin service — registered under ``nemo.services``.

Mounts three routers under ``/apis/insights/v2/workspaces/{workspace}/...``:

* ``/agent_registrations`` — registered agents under test
* ``/insights``            — analyst-produced findings
* ``/insight_traces``      — join entity between Insights and intake traces
"""

from __future__ import annotations

from typing import ClassVar

from nemo_platform_plugin.service import NemoService, RouterSpec

from nemo_insights_plugin.api.agent_registrations import build_agent_registrations_router
from nemo_insights_plugin.api.insight_traces import build_insight_traces_router
from nemo_insights_plugin.api.insights import build_insights_router


class InsightsPluginService(NemoService):
    """Mounted at ``/apis/insights/...`` by the platform."""

    name: ClassVar[str] = "insights"
    dependencies: ClassVar[list[str]] = []

    def get_routers(self) -> list[RouterSpec]:
        prefix = "/v2/workspaces/{workspace}"
        return [
            RouterSpec(
                build_agent_registrations_router(),
                tag="Insights · Agent Registrations",
                description="CRUD for registered agents under test.",
                prefix=prefix,
            ),
            RouterSpec(
                build_insights_router(),
                tag="Insights · Insights",
                description="CRUD for analyst-produced insights.",
                prefix=prefix,
            ),
            RouterSpec(
                build_insight_traces_router(),
                tag="Insights · Insight Traces",
                description="CRUD for Insight↔trace associations.",
                prefix=prefix,
            ),
        ]
