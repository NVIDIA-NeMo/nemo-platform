# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command-tree and placeholder tests."""

import pytest
import typer
from nemo_eval_author_plugin import cli
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    return cli.EvalAuthorCLI().get_cli()


def test_help_lists_discover(app: typer.Typer) -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "discover" in result.output


def test_placeholder_verbs_refuse_to_run_and_name_their_tickets(app: typer.Typer) -> None:
    for command, ticket in (
        ("audit", "ASE-676"),
        ("propose", "ASE-675"),
        ("run", "ASE-673"),
        ("doctor", "ASE-678"),
    ):
        result = runner.invoke(app, [command])

        assert result.exit_code == 1, result.output
        assert ticket in result.output
