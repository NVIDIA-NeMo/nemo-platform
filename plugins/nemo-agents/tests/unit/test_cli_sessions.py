# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``nemo agents sessions`` management commands."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import call, patch

import pytest
from nemo_agents_plugin.cli import AgentsCLI
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def app():
    return AgentsCLI().get_cli()


def _sessions_response() -> dict[str, Any]:
    return {
        "data": [
            {
                "id": "session-id",
                "name": "debug-auth",
                "workspace": "default",
                "status": "active",
                "deployment_id": "deployment-id",
                "first_active_at": "2026-09-01T15:00:00Z",
                "last_active_at": "2026-09-01T15:05:00Z",
                "expires_at": "2026-09-01T16:05:00Z",
                "created_at": "2026-09-01T14:59:00Z",
            }
        ],
        "pagination": {
            "current_page": 1,
            "current_page_size": 1,
            "total_pages": 1,
            "total_results": 1,
        },
        "sort": "-created_at",
        "filter": {},
    }


def test_sessions_help_exposes_management_scope_without_pagination_or_delete(app) -> None:
    result = runner.invoke(app, ["sessions", "--help"])

    assert result.exit_code == 0
    for command in ("list", "get", "close"):
        assert command in result.stdout
    assert "delete" not in result.stdout

    list_help = runner.invoke(app, ["sessions", "list", "--help"])
    assert list_help.exit_code == 0
    for option in ("--agent-deployment", "--format", "--no-truncate"):
        assert option in list_help.stdout
    for option in ("--page", "--page-size"):
        assert option not in list_help.stdout


def test_sessions_list_defaults_to_newest_first_api_table(app) -> None:
    response = _sessions_response()
    with patch("nemo_agents_plugin.cli._api_request", return_value=response) as api_request:
        result = runner.invoke(app, ["sessions", "list", "--base-url", "http://test"])

    assert result.exit_code == 0, result.output
    api_request.assert_called_once_with(
        "GET",
        "http://test",
        "/apis/agents/v2/workspaces/default/sessions",
    )
    assert "debug-auth" in result.stdout
    assert "active" in result.stdout
    assert "deployment_id" in result.stdout
    assert "last_active_at" in result.stdout
    assert "expires_at" in result.stdout
    assert '"data"' not in result.stdout


@pytest.mark.parametrize("output_format", ["json", "yaml", "csv", "markdown", "raw"])
def test_sessions_list_supports_existing_output_formats(app, output_format: str) -> None:
    response = _sessions_response()
    with patch("nemo_agents_plugin.cli._api_request", return_value=response):
        result = runner.invoke(app, ["sessions", "list", "--format", output_format])

    assert result.exit_code == 0, result.output
    assert "debug-auth" in result.stdout
    if output_format == "json":
        assert json.loads(result.stdout) == response


def test_sessions_list_filters_by_deployment_name(app) -> None:
    response = _sessions_response()
    with patch(
        "nemo_agents_plugin.cli._api_request",
        side_effect=[{"id": "deployment-id", "name": "fabric-deployment"}, response],
    ) as api_request:
        result = runner.invoke(
            app,
            ["sessions", "list", "--agent-deployment", "fabric-deployment", "--format", "json"],
        )

    assert result.exit_code == 0, result.output
    assert api_request.call_args_list == [
        call(
            "GET",
            "http://localhost:8080",
            "/apis/agents/v2/workspaces/default/deployments/fabric-deployment",
        ),
        call(
            "GET",
            "http://localhost:8080",
            "/apis/agents/v2/workspaces/default/sessions?filter%5Bdeployment_id%5D=deployment-id",
        ),
    ]


@pytest.mark.parametrize("deployment", [None, {}, {"id": None}, {"id": ""}, {"id": 123}])
def test_sessions_list_rejects_invalid_deployment_response(app, deployment: Any) -> None:
    with patch("nemo_agents_plugin.cli._api_request", return_value=deployment) as api_request:
        result = runner.invoke(app, ["sessions", "list", "--agent-deployment", "fabric-deployment"])

    assert result.exit_code == 1
    assert "Deployment 'fabric-deployment' returned an invalid response" in result.stderr
    api_request.assert_called_once_with(
        "GET",
        "http://localhost:8080",
        "/apis/agents/v2/workspaces/default/deployments/fabric-deployment",
    )


def test_sessions_list_rejects_empty_deployment_filter(app) -> None:
    with patch("nemo_agents_plugin.cli._api_request") as api_request:
        result = runner.invoke(app, ["sessions", "list", "--agent-deployment", ""])

    assert result.exit_code == 2
    assert "--agent-deployment must not be empty" in result.stderr
    api_request.assert_not_called()


def test_sessions_get_prints_full_session_json(app) -> None:
    session = _sessions_response()["data"][0]
    with patch("nemo_agents_plugin.cli._api_request", return_value=session) as api_request:
        result = runner.invoke(app, ["sessions", "get", "debug-auth", "--base-url", "http://test"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == session
    api_request.assert_called_once_with(
        "GET",
        "http://test",
        "/apis/agents/v2/workspaces/default/sessions/debug-auth",
    )


def test_sessions_close_requires_confirmation(app) -> None:
    with patch("nemo_agents_plugin.cli._api_request") as api_request:
        result = runner.invoke(app, ["sessions", "close", "debug-auth"], input="n\n")

    assert result.exit_code == 1
    assert "cannot be resumed" in result.stdout
    api_request.assert_not_called()


def test_sessions_close_accepts_yes_and_calls_close_endpoint(app) -> None:
    with patch(
        "nemo_agents_plugin.cli._api_request", return_value={"name": "debug-auth", "status": "closed"}
    ) as api_request:
        result = runner.invoke(
            app,
            ["sessions", "close", "debug-auth", "--yes", "--workspace", "team-a", "--base-url", "http://test"],
        )

    assert result.exit_code == 0, result.output
    assert "Session 'debug-auth' closed." in result.stdout
    api_request.assert_called_once_with(
        "POST",
        "http://test",
        "/apis/agents/v2/workspaces/team-a/sessions/debug-auth/close",
    )
