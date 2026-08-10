# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from unittest.mock import patch

import typer
from nemo_agents_plugin.cli import AgentsCLI
from nemo_platform_plugin.cli import NemoCLI
from typer.testing import CliRunner


class _AnalystCLI(NemoCLI):
    name = "analyst"

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help="Analyst agent commands.")

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch."""

        @app.command()
        def run() -> None:
            typer.echo("analysis complete")

        return app


class _BrokenCLI(NemoCLI):
    name = "broken"

    def get_cli(self) -> typer.Typer:
        raise RuntimeError("broken extension")


def test_broken_plugin_does_not_hide_other_agent_clis(caplog) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="nemo_agents_plugin.cli"),
        patch(
            "nemo_agents_plugin.cli.discover_agent_cli",
            return_value={"broken": _BrokenCLI, "analyst": _AnalystCLI},
        ),
    ):
        app = AgentsCLI().get_cli()
    result = CliRunner().invoke(app, ["analyst", "run"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "analysis complete"
    assert "Failed to load agent CLI extension 'broken'; skipping" in caplog.text
