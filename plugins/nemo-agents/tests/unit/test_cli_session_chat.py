# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI contract tests for ``nemo agents chat``."""

from __future__ import annotations

from typing import Any
from unittest.mock import call, patch

import pytest
from nemo_agents_plugin.cli import AgentsCLI
from nemo_agents_plugin.entities import (
    NAT_WORKFLOW_CONFIG_FORMAT,
    NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    AgentDeployment,
    AgentSession,
    DeploymentStatus,
)
from typer.testing import CliRunner

runner = CliRunner()


def _deployment_response(
    *,
    name: str = "fabric-deployment",
    workspace: str = "default",
    config_format: str = NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    status: DeploymentStatus = "running",
    endpoint: str = "http://127.0.0.1:9001",
) -> dict[str, Any]:
    response = AgentDeployment(
        name=name,
        workspace=workspace,
        agent="fabric-agent",
        config={"config_format": config_format},
        status=status,
        endpoint=endpoint,
    ).model_dump(mode="json")
    response["id"] = "deployment-id"
    return response


def _session_response(
    *,
    name: str = "debug-auth",
    workspace: str = "default",
    deployment_id: str = "deployment-id",
) -> dict[str, Any]:
    response = AgentSession(
        name=name,
        workspace=workspace,
        deployment_id=deployment_id,
    ).model_dump(mode="json")
    response["id"] = "session-id"
    return response


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


def test_session_chat_creates_named_session_and_passes_values_to_transport() -> None:
    app = AgentsCLI().get_cli()
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch(
            "nemo_agents_plugin.cli._api_request",
            side_effect=[_deployment_response(), _session_response()],
        ) as api_request,
        patch("nemo_agents_plugin.cli._run_resolved_session_chat") as run_chat,
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
                "--timeout",
                "42",
            ],
        )

    assert result.exit_code == 0, result.stderr
    assert api_request.call_args_list == [
        call(
            "GET",
            "http://localhost:8080",
            "/apis/agents/v2/workspaces/default/deployments/fabric-deployment",
        ),
        call(
            "POST",
            "http://localhost:8080",
            "/apis/agents/v2/workspaces/default/sessions",
            json_body={"deployment_id": "deployment-id", "name": "debug-auth"},
        ),
    ]
    run_chat.assert_called_once()
    run_kwargs = run_chat.call_args.kwargs
    assert run_kwargs["base_url"] == "http://localhost:8080"
    assert run_kwargs["workspace"] == "default"
    assert run_kwargs["input"] == "Help me debug this"
    assert run_kwargs["timeout"] == 42.0
    assert run_kwargs["deployment"].name == "fabric-deployment"
    assert run_kwargs["session"].name == "debug-auth"
    assert run_kwargs["session_id"] == "session-id"


def test_session_chat_preserves_api_generated_session_name() -> None:
    generated_name = "fabric-deployment-a1b2c3d4"
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch(
            "nemo_agents_plugin.cli._api_request",
            side_effect=[_deployment_response(), _session_response(name=generated_name)],
        ) as api_request,
        patch("nemo_agents_plugin.cli._run_resolved_session_chat") as run_chat,
    ):
        result = runner.invoke(
            AgentsCLI().get_cli(),
            ["chat", "--agent-deployment", "fabric-deployment"],
        )

    assert result.exit_code == 0, result.stderr
    assert api_request.call_args_list[1] == call(
        "POST",
        "http://localhost:8080",
        "/apis/agents/v2/workspaces/default/sessions",
        json_body={"deployment_id": "deployment-id"},
    )
    assert run_chat.call_args.kwargs["session"].name == generated_name
    assert run_chat.call_args.kwargs["session_id"] == "session-id"


def test_session_chat_rejects_non_fabric_deployment_before_session_creation() -> None:
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch(
            "nemo_agents_plugin.cli._api_request",
            return_value=_deployment_response(config_format=NAT_WORKFLOW_CONFIG_FORMAT),
        ) as api_request,
        patch("nemo_agents_plugin.cli._run_resolved_session_chat") as run_chat,
    ):
        result = runner.invoke(
            AgentsCLI().get_cli(),
            ["chat", "--agent-deployment", "fabric-deployment"],
        )

    assert result.exit_code == 1
    assert "is not Fabric-backed" in result.stderr
    api_request.assert_called_once()
    run_chat.assert_not_called()


@pytest.mark.parametrize(
    ("status", "endpoint"),
    [
        ("starting", "http://127.0.0.1:9001"),
        ("running", ""),
    ],
)
def test_session_chat_rejects_unroutable_deployment_before_session_creation(
    status: DeploymentStatus,
    endpoint: str,
) -> None:
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch(
            "nemo_agents_plugin.cli._api_request",
            return_value=_deployment_response(status=status, endpoint=endpoint),
        ) as api_request,
        patch("nemo_agents_plugin.cli._run_resolved_session_chat") as run_chat,
    ):
        result = runner.invoke(
            AgentsCLI().get_cli(),
            ["chat", "--agent-deployment", "fabric-deployment"],
        )

    assert result.exit_code == 1
    assert "is not routable" in result.stderr
    api_request.assert_called_once()
    run_chat.assert_not_called()


@pytest.mark.parametrize(
    ("session_response", "message"),
    [
        ({"name": "debug-auth", "deployment_id": "deployment-id"}, "did not include a valid ID"),
        (_session_response(deployment_id="other-deployment-id"), "mismatched deployment or workspace"),
        (_session_response(name="different-name"), "different name than requested"),
    ],
)
def test_session_chat_rejects_invalid_session_creation_response(
    session_response: dict[str, Any],
    message: str,
) -> None:
    with (
        patch("nemo_agents_plugin.cli._is_interactive_session_chat", return_value=True),
        patch(
            "nemo_agents_plugin.cli._api_request",
            side_effect=[_deployment_response(), session_response],
        ),
        patch("nemo_agents_plugin.cli._run_resolved_session_chat") as run_chat,
    ):
        result = runner.invoke(
            AgentsCLI().get_cli(),
            [
                "chat",
                "--agent-deployment",
                "fabric-deployment",
                "--session-name",
                "debug-auth",
            ],
        )

    assert result.exit_code == 1
    assert message in result.stderr
    run_chat.assert_not_called()
