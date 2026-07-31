# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scaffolding tests: the command tree exists, and every verb still refuses to run.

The entry-point cases cover the ``pyproject.toml`` wiring that nothing else exercises. A
typo in the key or the import path does not fail an import; it just makes ``nemo agents
eval-author`` quietly missing from the CLI, which no unit test of this module would catch.
The class is registered twice — canonically under ``nemo.cli.agents`` and, for backward
compatibility, under ``nemo.cli`` — so both groups are asserted.
"""

from importlib.metadata import EntryPoint, entry_points

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


def _eval_author_entry_point(group: str = "nemo.cli") -> EntryPoint:
    matches = [entry for entry in entry_points(group=group) if entry.name == "eval-author"]
    assert matches, f"no {group} entry point named 'eval-author'; reinstall the plugin with uv sync"
    return matches[0]


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


@pytest.mark.parametrize("group", ["nemo.cli.agents", "nemo.cli"])
def test_entry_point_key_matches_the_cli_name(group: str) -> None:
    """Discovery rejects a plugin whose entry-point key differs from its ``name``."""
    assert _eval_author_entry_point(group).value == "nemo_eval_author_plugin.cli:EvalAuthorCLI"
    assert cli.EvalAuthorCLI.name == "eval-author"


@pytest.mark.parametrize("group", ["nemo.cli.agents", "nemo.cli"])
def test_entry_point_loads_the_cli_class(group: str) -> None:
    assert _eval_author_entry_point(group).load() is cli.EvalAuthorCLI


def _mounted_under_agents() -> typer.Typer:
    """The mount `AgentsCLI` performs, without importing the agents plugin."""
    agents = typer.Typer()
    agents.add_typer(cli.EvalAuthorCLI().get_cli(), name="eval-author")
    root = typer.Typer()
    root.add_typer(agents, name="agents")
    return root


@pytest.mark.parametrize(("command", "ticket"), _PLACEHOLDER_VERBS)
def test_verb_is_reachable_under_agents_and_names_that_path(command: str, ticket: str) -> None:
    """The placeholder message must quote the path the caller typed, not a hardcoded one."""
    result = runner.invoke(_mounted_under_agents(), ["agents", "eval-author", command], prog_name="nemo")

    assert result.exit_code == 1, result.output
    assert f"`nemo agents eval-author {command}` is not implemented yet ({ticket})." in result.output


@pytest.mark.parametrize(("command", "ticket"), _PLACEHOLDER_VERBS)
def test_legacy_top_level_path_still_works(command: str, ticket: str) -> None:
    root = typer.Typer()
    root.add_typer(cli.EvalAuthorCLI().get_cli(), name="eval-author")

    result = runner.invoke(root, ["eval-author", command], prog_name="nemo")

    assert result.exit_code == 1, result.output
    assert f"`nemo eval-author {command}` is not implemented yet ({ticket})." in result.output
