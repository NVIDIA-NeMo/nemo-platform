# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Eval Author plugin CLI — ``nemo agents eval-author ...`` subcommands.

The same class is registered under both ``nemo.cli.agents`` and ``nemo.cli``, so every
verb is reachable as ``nemo agents eval-author <verb>`` (canonical) and as ``nemo
eval-author <verb>`` (retained for backward compatibility).

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


def _not_implemented(ctx: typer.Context, ticket: str) -> NoReturn:
    """Fail loudly, so a placeholder verb can never be mistaken for a successful run.

    The message quotes ``ctx.command_path`` rather than a hardcoded path, so it names
    whichever of the two mount points the caller actually used.
    """
    typer.echo(f"`{ctx.command_path}` is not implemented yet ({ticket}).", err=True)
    raise typer.Exit(code=1)


class EvalAuthorCLI(NemoCLI):
    """``nemo agents eval-author ...`` subcommands."""

    name: ClassVar[str] = "eval-author"
    description: ClassVar[str] = "NeMo Eval Author commands."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            """Force subcommand dispatch even when only one verb is registered."""

        @app.command("discover")
        def discover(ctx: typer.Context) -> None:
            """Discover candidate evaluation cases from agent traces."""
            # TODO(ASE-677): declare flags and wire discovery.
            _not_implemented(ctx, "ASE-677")

        @app.command("audit")
        def audit(ctx: typer.Context) -> None:
            """Audit an existing eval suite for coverage gaps."""
            # TODO(ASE-676): declare flags and wire the audit.
            _not_implemented(ctx, "ASE-676")

        @app.command("propose")
        def propose(ctx: typer.Context) -> None:
            """Propose eval suite additions for review."""
            # TODO(ASE-675): declare flags and wire the proposal.
            _not_implemented(ctx, "ASE-675")

        @app.command("run")
        def run(ctx: typer.Context) -> None:
            """Run the Eval Author pipeline end to end."""
            # TODO(ASE-673): declare flags and wire the pipeline to run_eval_author.
            _not_implemented(ctx, "ASE-673")

        @app.command("doctor")
        def doctor(ctx: typer.Context) -> None:
            """Diagnose Eval Author setup: credentials, platform, runtime."""
            # TODO(ASE-678): report the prerequisites the other verbs gate on.
            _not_implemented(ctx, "ASE-678")

        return app
