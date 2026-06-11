# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI overrides: submit accepts a job JSON file instead of ``--spec``."""

import json
from collections.abc import Callable
from pathlib import Path

import typer

from nemo_automodel_plugin.schema import AutomodelJobInput

_JOB_JSON_HELP = "Path to Automodel job JSON (AutomodelJobInput schema)."


def load_job_json(path: Path) -> str:
    """Load and validate job JSON; return canonical JSON string for ``--spec``."""
    data = json.loads(path.read_text())
    validated = AutomodelJobInput.model_validate(data)
    return validated.model_dump_json()


def apply_automodel_job_cli_overrides(group: typer.Typer) -> None:
    """Flat ``automodel`` CLI: ``submit JOB.json``; ``run`` is disabled."""
    _replace_job_run_disabled(group)
    _replace_job_submit(group)


def _pluck_callback(group: typer.Typer, verb: str) -> Callable[..., None]:
    command = next((c for c in group.registered_commands if c.name == verb), None)
    if command is None or command.callback is None:
        raise RuntimeError(f"missing {verb!r} callback to override")
    return command.callback


def _drop_command(group: typer.Typer, name: str) -> None:
    group.registered_commands = [c for c in group.registered_commands if c.name != name]


def _replace_job_run_disabled(group: typer.Typer) -> None:
    _drop_command(group, "run")

    @group.command("run")
    def run(
        _typer_ctx: typer.Context,
        _job_json: Path | None = typer.Argument(
            None,
            metavar="JOB_JSON",
            help=_JOB_JSON_HELP,
        ),
    ) -> None:
        typer.secho(
            "Automodel does not support local run. Submit to the platform API instead:\n"
            "  nemo customization automodel submit <job.json> -w <workspace>",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)


def _replace_job_submit(group: typer.Typer) -> None:
    original = _pluck_callback(group, "submit")

    @group.command("submit")
    def submit(
        typer_ctx: typer.Context,
        job_json: Path = typer.Argument(..., metavar="JOB_JSON", help=_JOB_JSON_HELP),
        workspace: str = typer.Option("default", "--workspace", "-w", help="Target workspace."),
        profile: str | None = typer.Option(None, "--profile"),
        cluster: str | None = typer.Option(None, "--cluster"),
        base_url: str | None = typer.Option(
            None,
            "--base-url",
            help=(
                "Override platform API host. If omitted: --cluster, then CLI context, "
                "then $NMP_BASE_URL, then http://localhost:8080."
            ),
        ),
        options: list[str] = typer.Option([], "-o", help="Backend option override, 'backend.key=value'."),
        options_file: Path | None = typer.Option(None, "--options-file"),
    ) -> None:
        spec_json = load_job_json(job_json)
        original(
            typer_ctx,
            spec=spec_json,
            spec_file=None,
            options=options,
            options_file=options_file,
            profile=profile,
            cluster=cluster,
            base_url=base_url,
            workspace=workspace,
            config=None,
            config_file=None,
        )
