# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the insights CLI placeholder."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from nemo_insights_plugin.cli import InsightsPluginCLI
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_app():
    return InsightsPluginCLI().get_cli()


def _make_response(status_code: int, json_data: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data if json_data is not None else {},
        request=httpx.Request("GET", "http://test"),
    )


class TestAnalyze:
    def test_placeholder_prints_registration_details(self, cli_app) -> None:
        reg_payload = {
            "name": "my-agent",
            "repo_url": "https://example.com/repo",
            "agent_description_path": "AGENT_DESCRIPTION.md",
            "eval_command": "nat eval --config evals.yml",
        }
        with patch("nemo_insights_plugin.cli.httpx.request", return_value=_make_response(200, reg_payload)):
            result = runner.invoke(cli_app, ["analyze", "--agent", "my-agent"])

        assert result.exit_code == 0, result.output
        assert "my-agent" in result.output
        assert "https://example.com/repo" in result.output
        assert "nat eval --config evals.yml" in result.output
        assert "not yet wired up" in result.output

    def test_missing_agent_exits_nonzero(self, cli_app) -> None:
        not_found = httpx.Response(
            status_code=404,
            json={"detail": "AgentRegistration 'missing' not found"},
            request=httpx.Request("GET", "http://test"),
        )

        def _raise(*args, **kwargs):
            return not_found

        with patch("nemo_insights_plugin.cli.httpx.request", side_effect=_raise):
            result = runner.invoke(cli_app, ["analyze", "--agent", "missing"])

        assert result.exit_code != 0


class TestRegistrationsList:
    def test_lists(self, cli_app) -> None:
        page = {"data": [{"name": "a"}, {"name": "b"}], "pagination": None}
        with patch("nemo_insights_plugin.cli.httpx.request", return_value=_make_response(200, page)):
            result = runner.invoke(cli_app, ["registrations", "list", "--workspace", "default"])
        assert result.exit_code == 0
        assert '"name": "a"' in result.output
