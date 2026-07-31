# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scaffolding tests: the command tree exists, and unimplemented verbs still refuse to run.

The entry-point cases cover the ``pyproject.toml`` wiring that nothing else exercises. A
typo in the key or the import path does not fail an import; it just makes ``nemo
eval-author`` quietly missing from the CLI, which no unit test of this module would catch.

``discover`` has shipped, so it is asserted on in ``discover/test_command.py`` instead. It
is listed in ``_IMPLEMENTED_VERBS`` here only so ``--help`` still has to show it.
"""

from importlib.metadata import EntryPoint, entry_points

import pytest
import typer
from nemo_eval_author_plugin import cli
from typer.testing import CliRunner

runner = CliRunner()

# Each verb is a placeholder owned by the child ticket named beside it.
_PLACEHOLDER_VERBS = [
    ("audit", "ASE-676"),
    ("propose", "ASE-675"),
    ("run", "ASE-673"),
    ("doctor", "ASE-769"),
]

_IMPLEMENTED_VERBS = ["discover"]


@pytest.fixture
def app() -> typer.Typer:
    return cli.EvalAuthorCLI().get_cli()


def _eval_author_entry_point() -> EntryPoint:
    matches = [entry for entry in entry_points(group="nemo.cli") if entry.name == "eval-author"]
    assert matches, "no nemo.cli entry point named 'eval-author'; reinstall the plugin with uv sync"
    return matches[0]


def test_help_lists_every_verb(app: typer.Typer) -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for command in [*(name for name, _ in _PLACEHOLDER_VERBS), *_IMPLEMENTED_VERBS]:
        assert command in result.output


@pytest.mark.parametrize(("command", "ticket"), _PLACEHOLDER_VERBS)
def test_verb_refuses_to_run_and_names_its_ticket(app: typer.Typer, command: str, ticket: str) -> None:
    result = runner.invoke(app, [command])

    assert result.exit_code == 1, result.output
    assert ticket in result.output


def test_entry_point_key_matches_the_cli_name() -> None:
    """Discovery rejects a plugin whose entry-point key differs from its ``name``."""
    assert _eval_author_entry_point().value == "nemo_eval_author_plugin.cli:EvalAuthorCLI"
    assert cli.EvalAuthorCLI.name == "eval-author"


def test_entry_point_loads_the_cli_class() -> None:
    assert _eval_author_entry_point().load() is cli.EvalAuthorCLI
