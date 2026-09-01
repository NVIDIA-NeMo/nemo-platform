# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI contract tests for ``nemo agents chat``."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from nemo_agents_plugin.cli import AgentsCLI
from typer.testing import CliRunner

runner = CliRunner()


def test_session_chat_help_describes_new_and_resumed_sessions() -> None:
    result = runner.invoke(AgentsCLI().get_cli(), ["chat", "--help"])

    assert result.exit_code == 0
    assert "Chat interactively with a new or existing deployed-agent session" in result.stdout
    assert "--input" in result.stdout
    assert "--agent-deployment" in result.stdout
    assert "--session" in result.stdout
    assert "--session-name" in result.stdout
    assert "--workspace" in result.stdout
    assert "--base-url" in result.stdout
    assert "--timeout" in result.stdout
    assert "--interactive" not in result.stdout


def test_session_chat_accepts_new_named_session_options() -> None:
    app = AgentsCLI().get_cli()
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch("nemo_agents_plugin.cli._platform_session_chat") as session_chat,
    ):
        result = runner.invoke(
            app,
            [
                "chat",
                "--agent-deployment",
                "fabric-deployment",
                "--session-name",
                "debug-auth",
                "--input",
                "Help me debug this",
                "--workspace",
                "team-a",
                "--base-url",
                "http://platform.test",
                "--timeout",
                "42",
            ],
        )

    assert result.exit_code == 0, result.stderr
    session_chat.assert_called_once_with(
        base_url="http://platform.test",
        workspace="team-a",
        agent_deployment="fabric-deployment",
        session=None,
        session_name="debug-auth",
        input="Help me debug this",
        timeout=42.0,
    )


def test_session_chat_accepts_existing_session_without_initial_input() -> None:
    app = AgentsCLI().get_cli()
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch("nemo_agents_plugin.cli._platform_session_chat") as session_chat,
    ):
        result = runner.invoke(app, ["chat", "--session", "debug-auth"])

    assert result.exit_code == 0, result.stderr
    session_chat.assert_called_once_with(
        base_url="http://localhost:8080",
        workspace="default",
        agent_deployment=None,
        session="debug-auth",
        session_name=None,
        input=None,
        timeout=300.0,
    )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ([], "Provide exactly one of --agent-deployment or --session"),
        (
            ["--agent-deployment", "fabric-deployment", "--session", "debug-auth"],
            "Provide exactly one of --agent-deployment or --session",
        ),
        (
            ["--session", "debug-auth", "--session-name", "replacement"],
            "--session-name can only be used with --agent-deployment",
        ),
        (["--agent-deployment", ""], "--agent-deployment must not be empty"),
        (["--session", ""], "--session must not be empty"),
        (["--agent-deployment", "fabric-deployment", "--session-name", ""], "--session-name must not be empty"),
        (["--agent-deployment", "fabric-deployment", "--input", ""], "--input must not be empty"),
    ],
)
def test_session_chat_rejects_invalid_selector_combinations(arguments: list[str], message: str) -> None:
    with patch("nemo_agents_plugin.cli._platform_session_chat") as session_chat:
        result = runner.invoke(AgentsCLI().get_cli(), ["chat", *arguments])

    assert result.exit_code == 2
    assert message in result.stderr
    session_chat.assert_not_called()


def test_session_chat_requires_an_interactive_terminal() -> None:
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=False),
        patch("nemo_agents_plugin.cli._platform_session_chat") as session_chat,
    ):
        result = runner.invoke(AgentsCLI().get_cli(), ["chat", "--session", "debug-auth"])

    assert result.exit_code == 2
    assert "Agent chat requires an interactive terminal" in result.stderr
    assert "nemo agents invoke" in result.stderr
    session_chat.assert_not_called()
