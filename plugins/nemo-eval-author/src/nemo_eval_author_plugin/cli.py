# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Eval Author commands under ``nemo agents eval-author``."""

import asyncio
from pathlib import Path
from typing import Annotated, ClassVar, NoReturn

import typer
from nemo_eval_author_plugin.discovery import run as discovery
from nemo_insights_plugin.contracts.checks import format_report
from nemo_platform_plugin.cli import NemoCLI


def _not_implemented(ctx: typer.Context, ticket: str) -> NoReturn:
    typer.echo(f"`{ctx.command_path}` is not implemented yet ({ticket}).", err=True)
    raise typer.Exit(code=1)


def _report_discovery(result: discovery.DiscoverResult) -> None:
    status = format_report(result.report.checks)
    if status:
        typer.echo(status)
    if result.report.run_command:
        typer.echo("")
        typer.echo(f"Run: {result.report.run_command}")

    typer.echo("")
    if result.dry_run:
        typer.echo("Dry run: no files were uploaded.")
        typer.echo("")
        typer.echo(result.markdown, nl=False)
    elif result.uploaded:
        remote_path = f"{result.report.agent}/{discovery.REPORT_FILENAME}"
        typer.echo(f"Uploaded {remote_path} to fileset '{discovery.FILESET_NAME}'.")
    else:
        typer.echo(f"Upload failed: {result.upload_error or 'unknown error'}", err=True)

    failures = sum(check.status == "fail" for check in result.report.checks)
    failures += not result.dry_run and not result.uploaded
    warnings = sum(check.status == "warn" for check in result.report.checks)
    failure_label = "failure" if failures == 1 else "failures"
    warning_label = "warning" if warnings == 1 else "warnings"
    status = "passed" if result.ok else "failed"
    typer.echo(f"Final overview: Discovery {status} with {failures} {failure_label} and {warnings} {warning_label}.")


class EvalAuthorCLI(NemoCLI):
    """``nemo agents eval-author ...`` subcommands."""

    name: ClassVar[str] = "eval-author"
    description: ClassVar[str] = "NeMo Eval Author commands."

    def get_cli(self) -> typer.Typer:
        app = typer.Typer(help=self.description, no_args_is_help=True)

        @app.callback()
        def _root() -> None:
            """Select an Eval Author command."""

        @app.command("discover")
        def discover(
            repo: Annotated[
                Path,
                typer.Option("--repo", help="Repository that contains the agent.", exists=True, file_okay=False),
            ] = Path(),
            agent: Annotated[
                str | None,
                typer.Option("--agent", help="Agent name. The default comes from optimizer.yaml or the directory."),
            ] = None,
            dry_run: Annotated[
                bool,
                typer.Option("--dry-run", help="Print discovery.md without an upload."),
            ] = False,
        ) -> None:
            """Inspect the repository and record its Harbor preflight.

            WARNING: Use this command only with a trusted repository.
            Agent imports execute module top-level code.
            """
            result = asyncio.run(
                discovery.discover(
                    discovery.DiscoverOptions(
                        repo_root=repo,
                        agent=agent,
                        dry_run=dry_run,
                    )
                )
            )
            _report_discovery(result)
            raise typer.Exit(code=0 if result.ok else 1)

        @app.command("audit")
        def audit(ctx: typer.Context) -> None:
            """Report coverage gaps in an existing eval suite."""
            # TODO(ASE-676): declare flags and wire the audit.
            _not_implemented(ctx, "ASE-676")

        @app.command("propose")
        def propose(ctx: typer.Context) -> None:
            """Propose eval suite additions for review."""
            # TODO(ASE-675): declare flags and wire the proposal.
            _not_implemented(ctx, "ASE-675")

        @app.command("run")
        def run(ctx: typer.Context) -> None:
            """Run the Eval Author pipeline."""
            # TODO(ASE-673): declare flags and wire the pipeline to run_eval_author.
            _not_implemented(ctx, "ASE-673")

        @app.command("doctor")
        def doctor(ctx: typer.Context) -> None:
            """Diagnose credentials, platform access, and the runtime."""
            # TODO(ASE-678): report the prerequisites the other verbs gate on.
            _not_implemented(ctx, "ASE-678")

        return app
