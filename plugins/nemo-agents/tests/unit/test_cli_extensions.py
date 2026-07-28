# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Callable
from unittest.mock import patch

import click
import typer
from nemo_agents_plugin.cli import AgentsCLI
from typer.main import get_command as typer_get_command
from typer.testing import CliRunner


def _agent_cli_factory(message: str) -> Callable[[], typer.Typer]:
    def factory() -> typer.Typer:
        app = typer.Typer(help=f"{message} agent commands.")

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch."""

        @app.command()
        def run() -> None:
            typer.echo(message)

        return app

    return factory


def _command_names(app: typer.Typer) -> set[str]:
    command = typer_get_command(app)
    assert isinstance(command, click.Group)
    return set(command.commands)


def test_plugin_can_contribute_agent_cli() -> None:
    with (
        patch(
            "nemo_agents_plugin.cli.discover_agent_cli",
            return_value={"insights.analyst": _agent_cli_factory("analysis complete")},
        ),
        patch("nemo_agents_plugin.cli.discover_entry_points", return_value={}),
    ):
        app = AgentsCLI().get_cli()

    result = CliRunner().invoke(app, ["analyst", "run"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "analysis complete"


def test_agent_cli_rejects_malformed_and_duplicate_names(caplog) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="nemo_agents_plugin.cli"),
        patch(
            "nemo_agents_plugin.cli.discover_agent_cli",
            return_value={
                "invalid": _agent_cli_factory("invalid"),
                "alpha.analyst": _agent_cli_factory("alpha"),
                "beta.analyst": _agent_cli_factory("beta"),
                "gamma.list": _agent_cli_factory("must not replace built-in"),
            },
        ),
        patch("nemo_agents_plugin.cli.discover_entry_points", return_value={}),
    ):
        app = AgentsCLI().get_cli()

    names = _command_names(app)
    assert "analyst" not in names
    assert "list" in names
    assert "expected '<plugin-name>.<agent-name>'" in caplog.text
    assert "multiple plugins registered it" in caplog.text
    assert "already registered under 'nemo agents'" in caplog.text


def test_agent_cli_cannot_replace_injected_job_or_function_commands(caplog) -> None:
    def entry_points(group: str) -> dict[str, object]:
        if group == "nemo.jobs":
            return {"agents.experimentalist": object()}
        if group == "nemo.functions":
            return {"agents.eval-author": object()}
        raise AssertionError(f"unexpected entry-point group: {group}")

    with (
        caplog.at_level(logging.WARNING, logger="nemo_agents_plugin.cli"),
        patch(
            "nemo_agents_plugin.cli.discover_agent_cli",
            return_value={
                "optimizer.experimentalist": _agent_cli_factory("experimentalist"),
                "evaluator.eval-author": _agent_cli_factory("eval author"),
            },
        ),
        patch("nemo_agents_plugin.cli.discover_entry_points", side_effect=entry_points),
    ):
        app = AgentsCLI().get_cli()

    names = _command_names(app)
    assert "experimentalist" not in names
    assert "eval-author" not in names
    assert caplog.text.count("already registered under 'nemo agents'") == 2


def test_invalid_agent_cli_factories_are_fault_isolated(caplog) -> None:
    def raises() -> typer.Typer:
        raise RuntimeError("broken factory")

    with (
        caplog.at_level(logging.WARNING, logger="nemo_agents_plugin.cli"),
        patch(
            "nemo_agents_plugin.cli.discover_agent_cli",
            return_value={
                "bad.not-callable": object(),
                "bad.raises": raises,
                "bad.wrong-type": lambda: object(),
                "good.analyst": _agent_cli_factory("working"),
            },
        ),
        patch("nemo_agents_plugin.cli.discover_entry_points", return_value={}),
    ):
        app = AgentsCLI().get_cli()

    names = _command_names(app)
    assert "analyst" in names
    assert "not-callable" not in names
    assert "raises" not in names
    assert "wrong-type" not in names
    assert "expected a zero-argument callable" in caplog.text
    assert "Failed to build agent CLI entry point 'bad.raises'" in caplog.text
    assert "factory returned object instead of typer.Typer" in caplog.text
