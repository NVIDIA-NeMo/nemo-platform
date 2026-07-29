# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Eval Author plugin CLI — ``nemo eval-author ...`` subcommands.

Scaffolding. Every verb is registered under its final name so the command tree is
discoverable and the child tickets have a landing spot, and each body exits non-zero
until its own ticket lands. Flags belong to those tickets, so nothing here declares
options yet.

This module imports nothing from ``eval_author``: those agents build their LLM client
while the class body executes, so importing one here would make the whole CLI require
``AUTHOR_*`` credentials — including the ``doctor`` verb whose job is to report that they
are missing. Experimentalist's CLI keeps its runner behind a lazily-assigned module
global for the same reason.
"""

from typing import ClassVar, NoReturn

import typer
from nemo_platform_plugin.cli import NemoCLI


def _not_implemented(command: str, ticket: str) -> NoReturn:
    """Fail loudly, so a placeholder verb can never be mistaken for a successful run."""
    typer.echo(f"`nemo eval-author {command}` is not implemented yet ({ticket}).", err=True)
    raise typer.Exit(code=1)


class EvalAuthorCLI(NemoCLI):
    """``nemo eval-author ...`` subcommands."""

    name: ClassVar[str] = "eval-author"
    description: ClassVar[str] = "NeMo Eval Author commands."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch even when only one verb is registered."""

        @app.command("discover")
        def discover() -> None:
            """Discover candidate evaluation cases from agent traces."""
            # TODO(ASE-677): declare flags and wire discovery.
            _not_implemented("discover", "ASE-677")

        @app.command("audit")
        def audit() -> None:
            """Audit an existing eval suite for coverage gaps."""
            # TODO(ASE-676): declare flags and wire the audit.
            _not_implemented("audit", "ASE-676")

        @app.command("propose")
        def propose() -> None:
            """Propose eval suite additions for review."""
            # TODO(ASE-675): declare flags and wire the proposal.
            _not_implemented("propose", "ASE-675")

        @app.command("run")
        def run() -> None:
            """Run the Eval Author pipeline end to end."""
            # TODO(ASE-673): declare flags and wire the pipeline to run_eval_author.
            _not_implemented("run", "ASE-673")

        @app.command("doctor")
        def doctor() -> None:
            """Diagnose Eval Author setup: credentials, platform, runtime."""
            # TODO(ASE-678): report the prerequisites the other verbs gate on.
            _not_implemented("doctor", "ASE-678")

        return app
