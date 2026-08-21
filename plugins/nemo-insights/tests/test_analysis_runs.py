# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The Insights analysis-runs facade over the generic ``agents.execute`` job."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import httpx
import pytest
from fastapi import HTTPException
from nemo_agents_plugin.entities import AgentInline
from nemo_agents_plugin.jobs.execute import ExecuteAgentJobConfig
from nemo_insights_plugin.analysis_runs import (
    CreateAnalysisRunRequest,
    build_execute_agent_job_config,
    create_analysis_run,
)
from nemo_platform import APIStatusError, AsyncNeMoPlatform
from pydantic import ValidationError

DEFAULT_MODEL = "default/big"
FAST_MODEL = "default/small"


def _request(**overrides: Any) -> CreateAnalysisRunRequest:
    """A valid request; the model pair is required so every call must carry it."""
    return CreateAnalysisRunRequest(
        agent=overrides.pop("agent", "demo-agent"),
        default_model=overrides.pop("default_model", DEFAULT_MODEL),
        fast_model=overrides.pop("fast_model", FAST_MODEL),
        **overrides,
    )


class _StubExecuteJobs:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response or {"name": "execute-a1b2", "status": "created"}
        self._error = error

    async def create(self, *, spec: dict[str, Any], name: str | None = None, workspace: str) -> dict[str, Any]:
        self.calls.append({"spec": spec, "name": name, "workspace": workspace})
        if self._error is not None:
            raise self._error
        return self._response


class _StubSdk:
    """Minimal stand-in for the request-scoped ``AsyncNeMoPlatform``."""

    def __init__(self, jobs: _StubExecuteJobs) -> None:
        self.agents = type("_Agents", (), {"jobs": type("_Jobs", (), {"execute": jobs})()})()


def _sdk(jobs: _StubExecuteJobs) -> AsyncNeMoPlatform:
    """The route only touches ``sdk.agents.jobs.execute``; cast past the concrete type."""
    return cast(AsyncNeMoPlatform, _StubSdk(jobs))


def _api_status_error(status_code: int, body: Any) -> APIStatusError:
    request = httpx.Request("POST", "http://platform/apis/agents/v2/workspaces/default/jobs/execute")
    response = httpx.Response(status_code, json=body, request=request)
    return APIStatusError("boom", response=response, body=body)


def test_execute_job_config_validates_against_the_real_job_schema() -> None:
    spec = build_execute_agent_job_config(_request(agent="demo-agent"), workspace="team-a")

    config = ExecuteAgentJobConfig.model_validate(spec)

    assert config.extension is not None
    assert config.extension.kind == "insights.analysis"
    assert config.extension.config == {"agent": "demo-agent", "workspace": "team-a"}


def test_analyst_is_submitted_inline_with_the_requested_models() -> None:
    """There is no Analyst Agent entity; the request composes one per run."""
    spec = build_execute_agent_job_config(_request(agent="demo-agent"), workspace="team-a")

    config = ExecuteAgentJobConfig.model_validate(spec)

    assert isinstance(config.agent, AgentInline)
    assert config.agent.config["name"] == "insights-analyst"
    assert config.agent.config["models"]["default"]["model"] == "default/big"
    assert config.agent.config["models"]["fast"]["model"] == "default/small"
    assert config.agent.config["harnesses"]["insights"]["settings"]["agent"] == "demo-agent"
    assert config.agent.config["harnesses"]["insights"]["settings"]["workspace"] == "team-a"


def test_read_scope_reaches_the_inline_analyst_settings() -> None:
    request = _request(since=datetime(2026, 8, 1, tzinfo=timezone.utc), evaluation_id="eval-123")

    config = ExecuteAgentJobConfig.model_validate(build_execute_agent_job_config(request, workspace="default"))

    assert isinstance(config.agent, AgentInline)
    settings = config.agent.config["harnesses"]["insights"]["settings"]
    assert settings["since"] == "2026-08-01T00:00:00+00:00"
    assert settings["evaluation_id"] == "eval-123"


def test_model_refs_are_required() -> None:
    """The pair lives only in the operator's CLI config, so the request must carry it."""
    with pytest.raises(ValidationError):
        CreateAnalysisRunRequest.model_validate({"agent": "demo-agent"})


def test_execute_job_config_omits_timeout_when_unset() -> None:
    spec = build_execute_agent_job_config(_request(agent="demo-agent"), workspace="default")

    assert "timeout_seconds" not in spec


def test_execute_job_config_carries_timeout_when_set() -> None:
    request = _request(timeout_seconds=120.0)

    spec = build_execute_agent_job_config(request, workspace="default")

    assert ExecuteAgentJobConfig.model_validate(spec).timeout_seconds == 120.0


async def test_create_analysis_run_submits_through_the_agents_sdk() -> None:
    jobs = _StubExecuteJobs()

    response = await create_analysis_run("team-a", _request(agent="demo-agent"), _sdk(jobs))

    assert response.job == {"name": "execute-a1b2", "status": "created"}
    assert jobs.calls[0]["workspace"] == "team-a"
    assert jobs.calls[0]["spec"]["agent"]["config"]["name"] == "insights-analyst"


async def test_create_analysis_run_leaves_job_name_to_the_jobs_service() -> None:
    """A fixed name would collide on the second run for the same agent."""
    jobs = _StubExecuteJobs()

    await create_analysis_run("default", _request(agent="demo-agent"), _sdk(jobs))

    assert jobs.calls[0]["name"] is None


async def test_create_analysis_run_forwards_an_explicit_job_name() -> None:
    jobs = _StubExecuteJobs()
    request = _request(name="nightly-demo-agent")

    await create_analysis_run("default", request, _sdk(jobs))

    assert jobs.calls[0]["name"] == "nightly-demo-agent"


async def test_create_analysis_run_surfaces_the_agents_service_error() -> None:
    error = _api_status_error(422, {"detail": "Agent 'insights-analyst' not found."})
    jobs = _StubExecuteJobs(error=error)

    with pytest.raises(HTTPException) as excinfo:
        await create_analysis_run("default", _request(agent="demo-agent"), _sdk(jobs))

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "Agent 'insights-analyst' not found."


async def test_create_analysis_run_falls_back_to_the_raw_error_body() -> None:
    jobs = _StubExecuteJobs(error=_api_status_error(500, {"message": "upstream exploded"}))

    with pytest.raises(HTTPException) as excinfo:
        await create_analysis_run("default", _request(agent="demo-agent"), _sdk(jobs))

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == {"message": "upstream exploded"}
