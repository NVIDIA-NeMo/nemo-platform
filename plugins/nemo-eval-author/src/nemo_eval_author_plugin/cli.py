# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Eval Author plugin CLI — ``nemo eval-author ...`` subcommands.

Every verb is registered under its final name so the command tree is discoverable and the
child tickets have a landing spot. The ones still unimplemented exit non-zero.

This module imports nothing from ``eval_author``: those agents build their LLM client while
the class body executes, so importing one here would make the whole CLI require ``AUTHOR_*``
credentials — including the ``doctor`` verb whose job is to report that they are missing.
``discovery.run`` is safe to import because it defers the one module that builds a client.
Experimentalist's CLI keeps its runner behind a lazily-assigned module global for the same
reason.
"""

import asyncio
from pathlib import Path
from typing import Annotated, ClassVar, NoReturn

import typer
from nemo_eval_author_plugin.discovery import run as discovery
from nemo_eval_author_plugin.discovery.models import FILESET_NAME, JOB_CONFIG_FILENAME, Finding
from nemo_eval_author_plugin.discovery.report import run_target
from nemo_platform_plugin.cli import NemoCLI

_STATUS_MARK = {"pass": "  ok  ", "warn": " warn ", "fail": " FAIL "}

# Order the ladder's own sequence, so the printed report reads the way validation ran
# rather than the way findings happened to accumulate.
_GROUP_ORDER = ("config", "validation", "repo", "scout", "memory")


def _not_implemented(command: str, ticket: str) -> NoReturn:
    """Fail loudly, so a placeholder verb can never be mistaken for a successful run."""
    typer.echo(f"`nemo eval-author {command}` is not implemented yet ({ticket}).", err=True)
    raise typer.Exit(code=1)


def _echo_finding(finding: Finding) -> None:
    typer.echo(f"[{_STATUS_MARK[finding.status]}] {finding.group}/{finding.name}: {finding.message}")


def _report_discovery(result: discovery.DiscoverResult) -> None:
    """Print the run, then the verdict, because the verdict is what the reader came for."""
    record = result.report
    if result.reused:
        typer.echo(
            f"Nothing the previous report depended on has changed, so its verdict still holds "
            f"(revalidated {record.last_validated_at.isoformat()})."
        )
    else:
        findings = [*record.findings, *result.memory_findings]
        for group in _GROUP_ORDER:
            for finding in (item for item in findings if item.group == group):
                _echo_finding(finding)

    typer.echo("")
    target = run_target(record)
    if target is not None:
        source = record.config_source
        typer.echo(f"Harbor can run this repo's evals ({source.detail if source else 'unknown source'}).")
        if target.location == "repo":
            typer.echo(f"Run it from {record.repo_root}, using the config this repo already maintains:")
            typer.echo(f"  harbor job start -c {target.path}")
        else:
            typer.echo(f"Discovery wrote the config to fileset '{FILESET_NAME}' at {target.path}.")
            typer.echo(f"Fetch it into {record.repo_root}, then:")
            typer.echo(f"  harbor job start -c {JOB_CONFIG_FILENAME}")
        if record.required_env_vars:
            typer.echo(f"  Needs: {', '.join(item.name for item in record.required_env_vars)}")
    else:
        typer.echo("Harbor cannot run this repo's evals. Blocking:", err=True)
        for finding in record.blocking:
            call = f" ({finding.harbor_call})" if finding.harbor_call else ""
            typer.echo(f"  - {finding.name}: {finding.message}{call}", err=True)
            if finding.hint:
                typer.echo(f"    {finding.hint}", err=True)

    if result.dry_run:
        typer.echo("")
        typer.echo("Dry run: nothing was uploaded.")
    elif result.persisted:
        typer.echo("")
        typer.echo(f"Recorded to fileset '{FILESET_NAME}' under {record.agent}/.")
    else:
        typer.echo("")
        typer.echo("Discovery could not be recorded, so a later run has nothing to read.", err=True)


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
        def discover(
            repo: Annotated[
                Path,
                typer.Option("--repo", help="Agent repository to inspect.", exists=True, file_okay=False),
            ] = Path(),
            agent: Annotated[
                str | None,
                typer.Option("--agent", help="Agent name. Defaults to optimizer.yaml, else the directory name."),
            ] = None,
            workspace: Annotated[str, typer.Option("--workspace", help="Platform workspace.")] = "default",
            base_url: Annotated[
                str | None,
                typer.Option("--base-url", help="Platform base URL. Defaults to the active context."),
            ] = None,
            env_backend: Annotated[
                str | None,
                typer.Option("--env-backend", help="Harbor environment type to assume when the repo names none."),
            ] = None,
            fix: Annotated[
                bool,
                typer.Option("--fix/--no-fix", help="Let an LLM scout propose fixes for a config that failed."),
            ] = False,
            refresh: Annotated[
                bool,
                typer.Option("--refresh", help="Revalidate even when nothing the last report depended on moved."),
            ] = False,
            dry_run: Annotated[
                bool,
                typer.Option("--dry-run", help="Print the findings and config without uploading anything."),
            ] = False,
        ) -> None:
            """Find and validate how this repo runs Harbor evals, then record it."""
            result = asyncio.run(
                discovery.discover(
                    discovery.DiscoverOptions(
                        repo_root=repo,
                        agent=agent,
                        workspace=workspace,
                        base_url=base_url,
                        env_backend=env_backend,
                        fix=fix,
                        refresh=refresh,
                        dry_run=dry_run,
                    )
                )
            )
            _report_discovery(result)
            if result.dry_run:
                typer.echo("")
                typer.echo(result.markdown)
                if result.job_config:
                    typer.echo(result.job_config)
            # Non-zero on an unrunnable config is what makes this usable as a gate in CI.
            raise typer.Exit(code=0 if result.ok else 1)

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
