# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level Insights analysis-run request helpers.

This module is intentionally a thin facade over the generic ``agents.execute``
job. The current ``AnalyzeJob`` can continue to run side-by-side while this
path exercises the Analyst-as-Agent implementation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from nemo_insights_plugin._perms import AnalysisRunPerms
from nemo_insights_plugin.analyst.agent_config import AGENT_CONFIG_FORMAT, build_analyst_agent_config
from nemo_insights_plugin.authz import scope
from nemo_platform import APIStatusError, AsyncNeMoPlatform
from nemo_platform_plugin.authz import CallerKind, path_rule
from nemo_platform_plugin.dependencies import get_sdk_client
from pydantic import BaseModel, Field

INSIGHTS_ANALYSIS_EXTENSION_KIND = "insights.analysis"

router = APIRouter(tags=["Insights Analysis Runs"])


class CreateAnalysisRunRequest(BaseModel):
    """Client-facing request to run the Insights Analyst through ``agents.execute``."""

    agent: str = Field(description="Agent whose telemetry should be analyzed.")
    default_model: str = Field(
        description=(
            "Workspace-qualified Model Entity ref ('<workspace>/<name>') the Analyst uses for "
            "analysis work. Required: the model pair is the operator's choice and is not "
            "persisted anywhere the Platform process can read it."
        ),
    )
    fast_model: str = Field(
        description=(
            "Workspace-qualified Model Entity ref used for context summarization. Required for "
            "the same reason as default_model."
        ),
    )
    ethos: str | None = Field(
        default=None,
        description=(
            "Optional Ethos Markdown for the agent under test. Sent inline rather than as a "
            "reference: the execute job's Fabric adapter has no Files access."
        ),
    )
    since: datetime | None = Field(
        default=None,
        description="Optional lower bound enforced on the Analyst's trace/span reads.",
    )
    evaluation_id: str | None = Field(
        default=None,
        description="Optional run scope AND-pinned onto every span read.",
    )
    name: str | None = Field(
        default=None,
        description="Optional job name. Omit to let the Jobs service generate a unique one.",
    )
    timeout_seconds: float | None = Field(default=None, gt=0, description="Optional execute job timeout.")


class CreateAnalysisRunResponse(BaseModel):
    """Response returned after creating the backing execute-agent job."""

    job: dict[str, Any]


@router.post("/analysis-runs", response_model=CreateAnalysisRunResponse)
@scope.write
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[AnalysisRunPerms.CREATE])
async def create_analysis_run(
    workspace: str,
    request: CreateAnalysisRunRequest,
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> CreateAnalysisRunResponse:
    """Create an Insights analysis run backed by the generic ``agents.execute`` job."""
    spec = build_execute_agent_job_config(request, workspace=workspace)
    try:
        # A ``None`` name is omitted from the request body so the Jobs service
        # generates a unique one; a fixed name would collide on the second run
        # for the same agent.
        job = await sdk.agents.jobs.execute.create(spec=spec, name=request.name, workspace=workspace)
    except APIStatusError as exc:
        # Surface the Agents service's own error rather than a bare 500 — a
        # missing Analyst Agent entity or an invalid config shows up here.
        raise HTTPException(status_code=exc.status_code, detail=_error_detail(exc)) from exc
    return CreateAnalysisRunResponse(job=job)


def build_execute_agent_job_config(request: CreateAnalysisRunRequest, *, workspace: str) -> dict[str, Any]:
    """Translate a high-level Insights request into a generic execute-agent job config."""
    extension_config: dict[str, Any] = {
        "agent": request.agent,
        "workspace": workspace,
    }
    payload: dict[str, Any] = {
        "agent": _inline_analyst(request, workspace=workspace),
        "input": _analysis_prompt(request.agent),
        "extension": {
            "kind": INSIGHTS_ANALYSIS_EXTENSION_KIND,
            "config": extension_config,
        },
    }
    if request.timeout_seconds is not None:
        payload["timeout_seconds"] = request.timeout_seconds

    return payload


def _inline_analyst(request: CreateAnalysisRunRequest, *, workspace: str) -> dict[str, Any]:
    """Build the ``agent`` arm of the execute job as an inline definition.

    The Analyst has no Agent entity: its config is composed here from the
    request's model pair and read scope. ``ExecuteAgentJobConfig.agent`` also
    accepts an entity ref, so pointing a run at a stored Analyst is a small
    change if a use case appears.
    """
    return {
        # AgentInline defaults to the legacy NAT format, matching the Agent
        # entity; the Analyst is a Fabric spec agent, so say so explicitly.
        "config_format": AGENT_CONFIG_FORMAT,
        "config": build_analyst_agent_config(
            agent=request.agent,
            workspace=workspace,
            default_model=request.default_model,
            fast_model=request.fast_model,
            ethos=request.ethos,
            since=request.since,
            evaluation_id=request.evaluation_id,
        ),
    }


def _error_detail(error: APIStatusError) -> Any:
    """Unwrap the Agents service's ``detail`` from a failed job-create call."""
    body: Any = error.body
    if isinstance(body, dict) and "detail" in body:
        return body["detail"]
    return body if body is not None else error.message


def _analysis_prompt(agent: str) -> str:
    return f"Analyze recent telemetry and maintain durable insights for {agent}."
