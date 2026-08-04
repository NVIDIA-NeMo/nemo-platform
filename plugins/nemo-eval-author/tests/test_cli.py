# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scaffolding tests: the command tree exists, and every verb still refuses to run."""

import pytest
import typer
from nemo_eval_author_plugin import cli
from typer.testing import CliRunner

runner = CliRunner()

# Each verb is a placeholder owned by the child ticket named beside it.
_PLACEHOLDER_VERBS = [
    ("discover", "ASE-677"),
    ("audit", "ASE-676"),
    ("propose", "ASE-675"),
    ("run", "ASE-673"),
    ("doctor", "ASE-678"),
]


@pytest.fixture
def app() -> typer.Typer:
    return cli.EvalAuthorCLI().get_cli()


def test_help_lists_every_verb(app: typer.Typer) -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for command, _ in _PLACEHOLDER_VERBS:
        assert command in result.output


@pytest.mark.parametrize(("command", "ticket"), _PLACEHOLDER_VERBS)
def test_verb_refuses_to_run_and_names_its_ticket(app: typer.Typer, command: str, ticket: str) -> None:
    result = runner.invoke(app, [command])

    assert result.exit_code == 1, result.output
    assert ticket in result.output


def test_not_implemented_quotes_the_invoked_command_path() -> None:
    """Placeholder messages use ``ctx.command_path``, not a hardcoded CLI string."""
    app = typer.Typer()

    @app.callback()
    def _root() -> None:
        """Force subcommand dispatch."""

    @app.command("probe")
    def probe(ctx: typer.Context) -> None:
        cli._not_implemented(ctx, "ASE-000")

    result = runner.invoke(app, ["probe"], prog_name="nemo")

    assert result.exit_code == 1, result.output
    assert "`nemo probe` is not implemented yet (ASE-000)." in result.output
